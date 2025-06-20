#!/usr/bin/env python3
"""
Load test script for k8s-metrix example API
Sends requests with linear increase from 1 to 100 requests per second over 5 minutes
"""

import asyncio
import aiohttp
import time
from datetime import datetime, timedelta
from rich.logging import RichHandler
from rich.console import Console
from rich.progress import Progress, TaskID
import logging
from typing import Optional

# Configure rich logging
console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(console=console)]
)
logger = logging.getLogger("load_test")

class LoadTester:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
        self.start_time: Optional[float] = None
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def send_request(self) -> bool:
        """Send a single request to the API"""
        if not self.session:
            raise RuntimeError("Session not initialized")
            
        try:
            async with self.session.get(f"{self.base_url}/") as response:
                self.total_requests += 1
                if response.status == 200:
                    self.successful_requests += 1
                    return True
                else:
                    self.failed_requests += 1
                    logger.warning(f"Request failed with status {response.status}")
                    return False
        except Exception as e:
            self.total_requests += 1
            self.failed_requests += 1
            logger.warning(f"Request failed with error: {e}")
            return False
    
    def calculate_current_rate(self, elapsed_seconds: float) -> float:
        """Calculate current target rate based on elapsed time"""
        # Linear increase from 1 to 100 requests per second over 300 seconds (5 minutes)
        if elapsed_seconds >= 300:
            return 100.0
        return 1.0 + (99.0 * elapsed_seconds / 300.0)
    
    async def run_load_test(self):
        """Run the load test with linear increase"""
        logger.info("🚀 Starting load test...")
        logger.info("📈 Target: Linear increase from 1 to 100 requests/second over 5 minutes")
        logger.info(f"🎯 Target URL: {self.base_url}")
        
        self.start_time = time.time()
        last_log_time = self.start_time
        last_request_count = 0
        
        with Progress() as progress:
            task = progress.add_task("Load Test Progress", total=300)  # 300 seconds = 5 minutes
            
            while True:
                current_time = time.time()
                elapsed_seconds = current_time - self.start_time
                
                # Stop after 5 minutes
                if elapsed_seconds >= 300:
                    logger.info("⏱️  5 minutes completed! Stopping load test...")
                    break
                
                # Calculate current target rate
                target_rate = self.calculate_current_rate(elapsed_seconds)
                
                # Calculate how many requests we should have sent by now
                # Integral of rate function: requests = t + (99*t²)/(2*300) where t is elapsed time
                target_total_requests = elapsed_seconds + (99 * elapsed_seconds**2) / (2 * 300)
                
                # Send requests to catch up to target
                requests_to_send = int(target_total_requests) - self.total_requests
                
                # Send the required requests
                if requests_to_send > 0:
                    tasks = [self.send_request() for _ in range(requests_to_send)]
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log progress every 10 seconds
                if current_time - last_log_time >= 10:
                    actual_rate = (self.total_requests - last_request_count) / (current_time - last_log_time)
                    success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
                    
                    elapsed_minutes = int(elapsed_seconds // 60)
                    elapsed_secs = int(elapsed_seconds % 60)
                    
                    logger.info(
                        f"⏰ {elapsed_minutes:02d}:{elapsed_secs:02d} | "
                        f"📊 Target: {target_rate:.1f} req/s | "
                        f"📈 Actual: {actual_rate:.1f} req/s | "
                        f"📋 Total: {self.total_requests} | "
                        f"✅ Success: {success_rate:.1f}% | "
                        f"❌ Failed: {self.failed_requests}"
                    )
                    
                    last_log_time = current_time
                    last_request_count = self.total_requests
                
                # Update progress bar
                progress.update(task, completed=elapsed_seconds)
                
                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.1)
        
        # Final summary
        total_time = time.time() - self.start_time
        avg_rate = self.total_requests / total_time if total_time > 0 else 0
        success_rate = (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
        
        logger.info("=" * 60)
        logger.info("📊 LOAD TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"⏱️  Total Duration: {total_time:.1f} seconds")
        logger.info(f"📋 Total Requests: {self.total_requests}")
        logger.info(f"✅ Successful: {self.successful_requests}")
        logger.info(f"❌ Failed: {self.failed_requests}")
        logger.info(f"📈 Average Rate: {avg_rate:.2f} requests/second")
        logger.info(f"📊 Success Rate: {success_rate:.1f}%")
        logger.info("=" * 60)

async def main():
    """Main function to run the load test"""
    try:
        async with LoadTester() as tester:
            await tester.run_load_test()
    except KeyboardInterrupt:
        logger.info("🛑 Load test interrupted by user")
    except Exception as e:
        logger.error(f"❌ Load test failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
