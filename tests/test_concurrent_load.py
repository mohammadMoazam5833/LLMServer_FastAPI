"""
تست بارگذاری async برای 20 کاربر همزمان
استفاده: pytest tests/test_concurrent_load.py -v -s
"""
import pytest
import asyncio
import httpx
import logging
from typing import List
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Setting up console handler for better visibility
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8000"
NUM_USERS = 20
NUM_MESSAGES_PER_USER = 5
TIMEOUT = 60.0  # timeout برای هر request


class ConcurrentUser:
    """نمایندگی یک کاربر"""
    
    def __init__(self, user_id: int, api_key: str):
        self.user_id = user_id
        self.api_key = api_key
        self.client = httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT)
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
    
    async def send_chat_message(self, message: str, stream: bool = False) -> bool:
        """ارسال یک پیام چت"""
        payload = {
            "messages": [
                {"role": "user", "content": message}
            ],
            "model": "Qwen3-Coder-30B",
            "stream": stream,
            "max_tokens": 512,
        }
        
        headers = {"X-API-Key": self.api_key}
        
        try:
            start_time = time.time()
            resp = await self.client.post(
                "/v1/chat/completions",
                json=payload,
                headers=headers,
            )
            response_time = (time.time() - start_time) * 1000  # ms
            self.response_times.append(response_time)
            
            if resp.status_code == 200:
                self.successful_requests += 1
                logger.debug(f"✅ User {self.user_id}: Success ({response_time:.0f}ms)")
                return True
            else:
                self.failed_requests += 1
                logger.warning(f"❌ User {self.user_id}: Status {resp.status_code}")
                return False
        
        except Exception as e:
            self.failed_requests += 1
            logger.error(f"❌ User {self.user_id}: {e}")
            return False
    
    async def run(self, num_messages: int = NUM_MESSAGES_PER_USER):
        """اجرای تعداد معینی از درخواست‌ها"""
        tasks = []
        for i in range(num_messages):
            # بعضی‌ها stream، بعضی‌ها regular
            is_stream = i % 2 == 0
            msg = f"کاربر {self.user_id}: پیام شماره {i+1}. یک مثال کد {['Python', 'Java', 'JavaScript'][i % 3]} بنویس."
            tasks.append(self.send_chat_message(msg, stream=is_stream))
        
        results = await asyncio.gather(*tasks)
        return results
    
    async def close(self):
        """بستن connection"""
        await self.client.aclose()
    
    def get_stats(self):
        """آمار درخواست‌ها"""
        total = self.successful_requests + self.failed_requests
        success_rate = (self.successful_requests / total * 100) if total > 0 else 0
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        max_response_time = max(self.response_times) if self.response_times else 0
        
        return {
            "user_id": self.user_id,
            "total_requests": total,
            "successful": self.successful_requests,
            "failed": self.failed_requests,
            "success_rate": success_rate,
            "avg_response_time_ms": avg_response_time,
            "max_response_time_ms": max_response_time,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_20_users_basic():
    """تست ۲۰ کاربر همزمان - درخواست‌های پایه"""
    logger.info(f"🚀 شروع تست: {NUM_USERS} کاربر، {NUM_MESSAGES_PER_USER} پیام هر کاربر")
    
    # ایجاد کاربران
    users: List[ConcurrentUser] = []
    for i in range(NUM_USERS):
        api_key = f"sk-test-load-{i}"  # Note: این API keys باید در DB موجود باشند!
        user = ConcurrentUser(i, api_key)
        users.append(user)
    
    start_time = time.time()
    
    try:
        # اجرای همه کاربران همزمان
        tasks = [user.run(NUM_MESSAGES_PER_USER) for user in users]
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # جمع‌آوری آمار
        total_requests = 0
        total_successful = 0
        total_failed = 0
        all_response_times = []
        
        user_stats = []
        for user in users:
            stats = user.get_stats()
            user_stats.append(stats)
            total_requests += stats['total_requests']
            total_successful += stats['successful']
            total_failed += stats['failed']
            all_response_times.extend(user.response_times)
        
        # محاسبه آمار کلی
        success_rate = (total_successful / total_requests * 100) if total_requests > 0 else 0
        avg_response_time = sum(all_response_times) / len(all_response_times) if all_response_times else 0
        max_response_time = max(all_response_times) if all_response_times else 0
        min_response_time = min(all_response_times) if all_response_times else 0
        
        # چاپ نتایج
        print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║              📊 Concurrent Load Test Results                  ║
    ║══════════════════════════════════════════════════════════════║
    
    🎯 Test Configuration:
       • Users: {NUM_USERS}
       • Messages/User: {NUM_MESSAGES_PER_USER}
       • Total Requests: {total_requests}
       • Duration: {total_time:.2f} seconds
    
    📈 Results:
       • Successful: {total_successful} ✅
       • Failed: {total_failed} ❌
       • Success Rate: {success_rate:.2f}%
       • Requests/sec: {total_requests / total_time:.2f}
    
    ⏱️  Response Times:
       • Average: {avg_response_time:.2f} ms
       • Min: {min_response_time:.2f} ms
       • Max: {max_response_time:.2f} ms
    
    👥 Per-User Stats (sample):
    """)
        
        # نمایش آمار برخی کاربران
        for i, stats in enumerate(user_stats[:5]):  # فقط 5 کاربر اول
            print(f"       User {stats['user_id']}: {stats['successful']}/{stats['total_requests']} ✓ ({stats['success_rate']:.0f}%) | Avg: {stats['avg_response_time_ms']:.0f}ms")
        
        if NUM_USERS > 5:
            print(f"       ... ({NUM_USERS - 5} more users)")
        
        print(f"""    
    ╚══════════════════════════════════════════════════════════════╝
    """)
        
        # Assertion برای بررسی موفقیت
        assert success_rate >= 90, f"Success rate {success_rate:.2f}% is below 90% threshold"
        assert total_failed == 0, f"There were {total_failed} failed requests"
        
    finally:
        # بستن تمام کلاینت‌ها
        tasks = [user.close() for user in users]
        await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_concurrent_20_users_stress():
    """تست استرس: ۲۰ کاربر - درخواست‌های بیشتر"""
    logger.info(f"🔥 شروع تست استرس: {NUM_USERS} کاربر، {NUM_MESSAGES_PER_USER * 2} پیام هر کاربر")
    
    users: List[ConcurrentUser] = []
    for i in range(NUM_USERS):
        api_key = f"sk-test-stress-{i}"
        user = ConcurrentUser(i, api_key)
        users.append(user)
    
    start_time = time.time()
    
    try:
        # اجرای با تعداد بیشتر درخواست
        tasks = [user.run(NUM_MESSAGES_PER_USER * 2) for user in users]
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        # جمع‌آوری آمار
        total_requests = 0
        total_successful = 0
        
        for user in users:
            stats = user.get_stats()
            total_requests += stats['total_requests']
            total_successful += stats['successful']
        
        success_rate = (total_successful / total_requests * 100) if total_requests > 0 else 0
        
        print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║           🔥 Stress Test Results ({NUM_USERS} Users)           ║
    ╚══════════════════════════════════════════════════════════════╝
    
       • Total Requests: {total_requests}
       • Successful: {total_successful}
       • Success Rate: {success_rate:.2f}%
       • Duration: {total_time:.2f}s
       • Throughput: {total_requests / total_time:.2f} req/sec
    """)
        
        assert success_rate >= 85, f"Stress test success rate {success_rate:.2f}% below threshold"
        
    finally:
        tasks = [user.close() for user in users]
        await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_api_health_check():
    """تست سلامت API"""
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get("/health")
        assert resp.status_code == 200, f"Health check failed: {resp.status_code}"
        logger.info("✅ API Health: OK")


if __name__ == "__main__":
    # اجرای مستقیم برای آزمایش
    asyncio.run(test_concurrent_20_users_basic())
