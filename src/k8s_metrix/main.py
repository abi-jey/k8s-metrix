from typing import List
from typing import Dict
from typing import Optional
from typing import Literal
from logging import getLogger
from asyncio import sleep
from asyncio import create_task
from asyncio import Task
from asyncio import Queue
import base64
import tempfile
import os
import json
from datetime import datetime
import aiohttp
import ssl
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False
from k8s_metrix.backends import FsBackend

logger = getLogger(__name__)

class K8sMetrix:
    def __init__(
            self,
            *,
            adapter_url: str = "",
            backend: Literal["fs", "redis"] = "fs",
            service_name: str = "",
            ) -> None:
        """
        Initialize the K8sMetrix instance.

        Args:
            adapter_url (str): URL of the metrix-adapter endpoint. Defaults to "http://localhost:8000".
            backend (str): Backend type for metrics storage. Defaults to "fs".
            service_name (str): Name of the service. If not provided, reads from SERVICE_NAME env var.
        """
        default_adapter_url = "https://metrix-system-service.metrix-system.svc.cluster.local:8000"
        self.adapter_url = adapter_url if adapter_url else default_adapter_url

        self.loop: Optional[Task] = None
        self._metrics_queue: Queue = Queue()
        self.backend = backend
        self._http_session: aiohttp.ClientSession = self._create_http_session()
        self.pod_name = os.getenv('HOSTNAME', 'unknown-pod')
        self.pod_namespace = self._get_pod_namespace()
        self.node_name = os.getenv('NODE_NAME', 'unknown-node')
        self.service_name = service_name if service_name else os.getenv('SERVICE_NAME', 'unknown-service')

    def _get_pod_namespace(self) -> str:
        """Read the pod namespace from the Kubernetes service account file."""
        try:
            with open('/var/run/secrets/kubernetes.io/serviceaccount/namespace', 'r') as f:
                logger.debug("[k8s-metrix]: Reading pod namespace from service account file")
                return f.read().strip()
        except (FileNotFoundError, IOError, PermissionError) as e:
            logger.warning(f"Failed to read namespace from service account file: {e}")
            return 'default'

    def _create_http_session(self) -> aiohttp.ClientSession:
        """Create an HTTP session with SSL verification disabled."""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        return aiohttp.ClientSession(connector=connector)


    async def start(self):
        """
        Start the K8sMetrix instance.
        """
        logger.debug(f"[k8s-metrix]: Starting K8sMetrix with adapter URL: {self.adapter_url}")
    
        self._metrics_queue = Queue()
        self._http_session = self._create_http_session()
        logger.debug(f"[k8s-metrix]: Client mode - connecting to adapter at {self.adapter_url}")
        logger.debug(f"[k8s-metrix]: Pod info - name: {self.pod_name}, namespace: {self.pod_namespace}, "
                        f"service: {self.service_name}, node: {self.node_name}")  # fmt: skip
        self.loop = create_task(self._daemon())
        logger.debug(f"[k8s-metrix]: K8sMetrix startup complete.")

    async def stop(self):
        """
        Stop the K8sMetrix instance and cleanup resources.
        """
        if self.loop:
            self.loop.cancel()
            try:
                await self.loop
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            except Exception as e:
                logger.debug(f"[k8s-metrix]: Error stopping daemon: {e}")
        
        if self._http_session:
            await self._http_session.close()
        
        logger.debug("[k8s-metrix]: K8sMetrix stopped.")


    async def _daemon(self):
        """
        The main loop of the K8sMetrix instance.
        """
        await self._client_daemon()

    async def _client_daemon(self):
        """
        Client daemon loop that sends queued metrics to the adapter.
        """
        while True:
            try:
                if not self._metrics_queue.empty():
                    # Collect all queued metrics
                    metrics_batch = []
                    while not self._metrics_queue.empty():
                        try:
                            metric = await self._metrics_queue.get()
                            metrics_batch.append(metric)
                        except Exception:
                            break
                    
                    if metrics_batch:
                        await self._send_metrics_to_adapter(metrics_batch)
                
                await sleep(5)
                logger.debug(f"[k8s-metrix]: Client daemon running. Queue size: {self._metrics_queue.qsize()}")
            except Exception as e:
                logger.error(f"[k8s-metrix]: Error in client daemon: {e}")
                await sleep(5)

    async def _server_daemon(self):
        """
        Server daemon loop for backend operations.
        """
        while True:
            await sleep(5)

    async def _send_metrics_to_adapter(self, metrics_batch: List[Dict]):
        """
        Send a batch of metrics to the adapter endpoint.
        """
        try:
            payload = {
                "pod_name": self.pod_name,
                "pod_namespace": self.pod_namespace,
                "service_name": self.service_name,
                "node_name": self.node_name,
                "metrics": metrics_batch,
                "timestamp": datetime.now().isoformat()
            }
            
            async with self._http_session.post(
                f"{self.adapter_url}/metrics",
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    logger.debug(f"[k8s-metrix]: Successfully sent {len(metrics_batch)} metrics to adapter")
                else:
                    logger.error(f"[k8s-metrix]: Failed to send metrics to adapter. Status: {response.status}, "
                               f"Response: {await response.text()}")  # fmt: skip
        except Exception as e:
            logger.error(f"[k8s-metrix]: Error sending metrics to adapter: {e}")

    async def add_metric(self, name: str, value: int, additional_info: Optional[Dict[str, str]] = None, 
                        metric_type: str = "gauge"):
        """
        Add custom metrics to the K8sMetrix instance.

        Args:
            name (str): The name of the metric.
            value (int): The value of the metric.
            additional_info (Optional[Dict[str, str]]): Additional metadata for the metric.
            metric_type (str): Type of metric. "counter" for rate-based metrics that will be 
                             averaged and saved as "{metric_name}_per_second", "gauge" for 
                             cumulative metrics like live connections (default).
        """
        if not isinstance(value, int):
            raise ValueError("Value must be an integer.")
        value = int(value)
        
        if metric_type not in ["counter", "gauge"]:
            raise ValueError("metric_type must be either 'counter' or 'gauge'")
        
        metric_data = {
            "name": name,
            "value": value,
            "timestamp": datetime.now().isoformat(),
            "metric_type": metric_type,
            "additional_info": additional_info or {}
        }
        
        logger.debug(f"[k8s-metrix]: Adding metric: {name}:{value} (type: {metric_type})")
        await self._metrics_queue.put(metric_data)
        logger.debug(f"[k8s-metrix]: Metric {name} added to queue. Current queue size: "
                    f"{self._metrics_queue.qsize()}")  # fmt: skip




def generate_private_key_and_csr(service_name: str, 
                                namespace: str = "default",
                                organization: str = "k8s-metrix", 
                                country: str = "US") -> tuple[bytes, bytes]:
    """
    Generate a private key and Certificate Signing Request (CSR).
    
    Args:
        service_name (str): The service name 
        namespace (str): The Kubernetes namespace (default: "default")
        organization (str): Organization name
        country (str): Country code
        
    Returns:
        tuple[bytes, bytes]: Private key and CSR in PEM format
    """
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Create proper common name for Kubernetes service
    common_name = f"{service_name}.{namespace}.svc"
    
    # Create certificate subject
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, country),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    
    # Generate CSR with proper DNS names for service
    csr = x509.CertificateSigningRequestBuilder().subject_name(
        subject
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(common_name),
            x509.DNSName(f"{service_name}.{namespace}"),
            x509.DNSName(service_name),
        ]),
        critical=False,
    ).sign(private_key, hashes.SHA256())
    
    # Serialize to PEM format
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    csr_pem = csr.public_bytes(serialization.Encoding.PEM)
    
    logger.info(f"Generated private key and CSR for {common_name}")
    return private_key_pem, csr_pem


def create_k8s_csr(csr_name: str, csr_pem: bytes, usages: Optional[List[str]] = None) -> bool:
    """
    Submit a Certificate Signing Request to Kubernetes.
    
    Args:
        csr_name (str): Name for the CSR resource in Kubernetes
        csr_pem (bytes): The CSR in PEM format
        usages (Optional[List[str]]): List of key usages for the certificate
        
    Returns:
        bool: True if CSR was successfully created, False otherwise
    """
    if not K8S_AVAILABLE:
        logger.error("Kubernetes client not available. Cannot create CSR.")
        return False
        
    # Import here to avoid issues when kubernetes is not available
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
        
    if usages is None:
        # Fix: Use client auth instead of server auth for service certificates
        usages = ["digital signature", "key encipherment", "client auth"]
    
    try:
        # Load Kubernetes configuration
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration")
    except config.ConfigException:
        try:
            config.load_kube_config()
            logger.info("Loaded kubeconfig from local file")
        except config.ConfigException as e:
            logger.error(f"Failed to load Kubernetes configuration: {e}")
            return False
    
    # Create Kubernetes API client
    v1 = client.CertificatesV1Api()
    
    # Encode CSR to base64
    csr_b64 = base64.b64encode(csr_pem).decode('utf-8')
    
    # Create CSR object
    csr_spec = client.V1CertificateSigningRequestSpec(
        request=csr_b64,
        signer_name="kubernetes.io/kube-apiserver-client",
        usages=usages
    )
    
    csr_metadata = client.V1ObjectMeta(name=csr_name)
    
    csr_object = client.V1CertificateSigningRequest(
        api_version="certificates.k8s.io/v1",
        kind="CertificateSigningRequest",
        metadata=csr_metadata,
        spec=csr_spec
    )
    
    try:
        # Submit CSR to Kubernetes
        response = v1.create_certificate_signing_request(body=csr_object)
        logger.info(f"Successfully created CSR: {response.metadata.name}")
        logger.info(f"CSR status: {response.status}")
        return True
        
    except ApiException as e:
        logger.error(f"Failed to create CSR: {e}")
        return False


def save_private_key_to_file(private_key_pem: bytes, file_path: str = "./k8s-metrix-key.pem"):
    """
    Save the private key to a file.
    
    Args:
        private_key_pem (bytes): The private key in PEM format
        file_path (str): Path where to save the private key
    """
    try:
        with open(file_path, 'wb') as f:
            f.write(private_key_pem)
        # Set restrictive permissions (owner read/write only)
        os.chmod(file_path, 0o600)
        logger.info(f"Private key saved to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save private key: {e}")


def wait_for_csr_approval(csr_name: str, timeout_seconds: int = 300) -> tuple[bool, Optional[bytes]]:
    """
    Wait for a Certificate Signing Request to be approved and retrieve the signed certificate.
    
    Args:
        csr_name (str): Name of the CSR resource in Kubernetes
        timeout_seconds (int): Maximum time to wait for approval (default: 5 minutes)
        
    Returns:
        tuple[bool, Optional[bytes]]: (success, certificate_pem)
            - success: True if CSR was approved and certificate retrieved
            - certificate_pem: The signed certificate in PEM format, or None if failed
    """
    if not K8S_AVAILABLE:
        logger.error("Kubernetes client not available. Cannot check CSR status.")
        return False, None
        
    # Import here to avoid issues when kubernetes is not available
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    import time
    
    try:
        # Use existing configuration (should already be loaded)
        v1 = client.CertificatesV1Api()
        
        logger.info(f"Waiting for CSR '{csr_name}' to be approved (timeout: {timeout_seconds}s)...")
        logger.info(f"💡 To approve the CSR manually, run: kubectl certificate approve {csr_name}")
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout_seconds:
            try:
                # Get the current CSR status
                csr = v1.read_certificate_signing_request(name=csr_name)
                
                # Check if CSR has been approved
                if csr.status and csr.status.conditions:
                    for condition in csr.status.conditions:
                        if condition.type == "Approved" and condition.status == "True":
                            logger.info("✓ CSR has been approved!")
                            
                            # Check if certificate is available
                            if csr.status.certificate:
                                # Decode the base64 certificate
                                cert_pem = base64.b64decode(csr.status.certificate)
                                logger.info("✓ Signed certificate retrieved successfully!")
                                return True, cert_pem
                            else:
                                logger.info("CSR approved but certificate not yet available, continuing to wait...")
                                
                        elif condition.type == "Denied" and condition.status == "True":
                            logger.error(f"✗ CSR has been denied: {condition.message}")
                            return False, None
                
                # Enhanced waiting message with command reminder
                check_count += 1
                elapsed = int(time.time() - start_time)
                remaining = timeout_seconds - elapsed
                
                if check_count % 3 == 0:  # Show command every 30 seconds (every 3rd check)
                    logger.info(f"⏳ Still waiting for approval... ({elapsed}s elapsed, {remaining}s remaining)")
                    logger.info(f"💡 Run: kubectl certificate approve {csr_name}")
                else:
                    logger.info(f"⏳ CSR still pending approval... ({elapsed}s elapsed, {remaining}s remaining)")
                
                time.sleep(10)  # Check every 10 seconds
                
            except ApiException as e:
                logger.error(f"Error checking CSR status: {e}")
                return False, None
        
        logger.error(f"✗ Timeout waiting for CSR approval after {timeout_seconds} seconds")
        return False, None
        
    except Exception as e:
        logger.error(f"Failed to wait for CSR approval: {e}")
        return False, None


def save_certificate_to_file(cert_pem: bytes, file_path: str = "./k8s-metrix-cert.pem"):
    """
    Save the signed certificate to a file.
    
    Args:
        cert_pem (bytes): The certificate in PEM format
        file_path (str): Path where to save the certificate
    """
    try:
        with open(file_path, 'wb') as f:
            f.write(cert_pem)
        # Set readable permissions for certificate
        os.chmod(file_path, 0o644)
        logger.info(f"Certificate saved to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save certificate: {e}")


def save_csr_to_file(csr_pem: bytes, file_path: str = "./k8s-metrix-csr.pem"):
    """
    Save the Certificate Signing Request to a file.
    
    Args:
        csr_pem (bytes): The CSR in PEM format
        file_path (str): Path where to save the CSR
    """
    try:
        with open(file_path, 'wb') as f:
            f.write(csr_pem)
        # Set readable permissions for CSR
        os.chmod(file_path, 0o644)
        logger.info(f"CSR saved to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save CSR: {e}")


def run_csr_workflow(service_name: str = "k8s-metrix-service", namespace: str = "default"):
    """
    Run the complete CSR workflow: generate key/CSR, submit to K8s, and save key.
    
    Args:
        service_name (str): Name of the Kubernetes service (default: "k8s-metrix-service")
        namespace (str): Kubernetes namespace (default: "default")
    """
    if not K8S_AVAILABLE:
        logger.warning("Kubernetes client not available. CSR functionality will be disabled.")
        return
        
    # Configuration
    csr_name = f"{service_name}-csr"
    full_service_name = f"{service_name}.{namespace}.svc"
    
    logger.info("Starting CSR workflow...")
    logger.info(f"Service: {full_service_name}")
    logger.info(f"CSR Name: {csr_name}")
    
    # Step 1: Generate private key and CSR
    try:
        private_key_pem, csr_pem = generate_private_key_and_csr(
            service_name=service_name,
            namespace=namespace,
            organization="k8s-metrix",
            country="US"
        )
        logger.info("✓ Generated private key and CSR")
        
        # Save CSR to file immediately after generation
        save_csr_to_file(csr_pem)
        logger.info("✓ CSR saved to file")
    except Exception as e:
        logger.error(f"Failed to generate private key and CSR: {e}")
        return
    
    # Step 2: Submit CSR to Kubernetes
    success = create_k8s_csr(csr_name, csr_pem)
    if success:
        logger.info("✓ Successfully submitted CSR to Kubernetes")
    else:
        logger.error("✗ Failed to submit CSR to Kubernetes")
        return
    
    # Step 3: Wait for CSR approval and retrieve the signed certificate
    logger.info("Waiting for CSR approval...")
    success, cert_pem = wait_for_csr_approval(csr_name, timeout_seconds=300)
    if success and cert_pem:
        logger.info("✓ CSR approved and certificate retrieved")
        # Step 4: Save the signed certificate to a file
        save_certificate_to_file(cert_pem)
        logger.info("✓ Certificate saved to file")
        # Step 5: Save private key to file
        save_private_key_to_file(private_key_pem)
        logger.info("✓ Private key saved to file")
        
        logger.info("CSR workflow completed successfully!")
        logger.info("Both private key and signed certificate are now available for use.")
    else:
        logger.error("✗ Failed to retrieve certificate or CSR was not approved")
        logger.info("You can manually approve the CSR and retrieve the certificate later:")
        logger.info(f"1. Approve the CSR: kubectl certificate approve {csr_name}")
        logger.info(f"2. Retrieve the signed certificate: kubectl get csr {csr_name} -o jsonpath='{{.status.certificate}}' | base64 -d > ./k8s-metrix-cert.pem")  # fmt: skip
        # Still save the private key even if approval failed
        save_private_key_to_file(private_key_pem)
        logger.info("✓ Private key saved to file")


if __name__ == "__main__":
    import asyncio
    import logging
    import argparse
    from rich.logging import RichHandler
    from rich.console import Console
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Generate and submit Kubernetes CSR for service certificates")
    parser.add_argument("--service-name", "-s", default="k8s-metrix-service", 
                       help="Name of the Kubernetes service (default: k8s-metrix-service)")
    parser.add_argument("--namespace", "-n", default="default", 
                       help="Kubernetes namespace (default: default)")
    args = parser.parse_args()
    
    # Set up rich logging
    console = Console()
    logging.basicConfig(level=logging.INFO,format="%(message)s",handlers=[RichHandler(console=console)])
    
    # Configure the logger for this module
    logger.setLevel(logging.INFO)
    
    # Display configuration
    logger.info(f"🚀 Starting CSR workflow for service: {args.service_name}.{args.namespace}.svc")
    
    # Run the CSR workflow with parsed arguments
    run_csr_workflow(service_name=args.service_name, namespace=args.namespace)
    
    # Optional: Run the K8sMetrix service
    # async def main():
    #     metrix = K8sMetrix(backend="fs")
    #     await metrix.start()
    # 
    # asyncio.run(main())
