import asyncio
import time
import httpx  # HTTP 요청 도구. 0.5에서 설치했다

def sync_version():
    start = time.perf_counter()
    for _ in range(10):
        time.sleep(1)
    print(f"동기: {time.perf_counter() - start:.1f}초")


async def one():
    await asyncio.sleep(1)


async def async_version():
    start = time.perf_counter()
    await asyncio.gather(*(one() for _ in range(10)))
    print(f"비동기: {time.perf_counter() - start:.1f}초")

async def work(n, fail=False):
    await asyncio.sleep(n)
    if fail:
        raise ValueError(f"작업 {n} 실패")
    print(f"작업 {n} 완료")
    return n

async def exp_gather():
    try:
        results = await asyncio.gather(work(1), work(2, fail=True), work(3))
        print("결과:", results)
    except ValueError as e:
        print("gather 기본 → 예외가 바로 올라옴:", e)
    await asyncio.sleep(2)

async def exp_gather_safe():
    results = await asyncio.gather(work(1), work(2, fail=True), work(3), return_exceptions=True)
    for r in results:
        print("실패" if isinstance(r, Exception) else "성공", r)


async def exp_taskgroup():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(work(1))
            tg.create_task(work(2, fail=True))
            tg.create_task(work(3))
    except* ValueError as eg:
        print("TaskGroup → 실패 묶음:", eg.exceptions)
    await asyncio.sleep(2)


async def exp_semaphore():
    sem = asyncio.Semaphore(5)

    async def limited(i):
        async with sem:
            await asyncio.sleep(1)
            return i

    start = time.perf_counter()
    await asyncio.gather(*(limited(i) for i in range(20)))
    print(f"Semaphore(5), 작업 20개: {time.perf_counter() - start:.1f}초")


async def slow():
    try:
        await asyncio.sleep(5)
        print("이 줄은 안 찍힘")
    except asyncio.CancelledError:
        print("취소됨 → 정리 중")
        raise


async def exp_timeout():
    try:
        async with asyncio.timeout(3):
            await slow()
    except TimeoutError:
        print("3초 초과 → TimeoutError")


async def fetch_one(client, sem, url):
    """URL 하나를 가져와서, 성공이든 실패든 항상 결과 딕셔너리 하나를 돌려준다."""
    async with sem:  # 빈자리가 날 때까지 기다렸다 들어간다 → 동시에 sem 크기만큼만 실행
        start = time.perf_counter()  # 시작 시각 (시간 재기용)
        try:
            # 요청을 보내고 응답을 기다린다. 기다리는 동안 다른 URL 요청이 진행된다
            r = await client.get(url)
            # 성공: 상태 코드를 기록한다 (500도 '응답은 왔음'이라 여기로 온다)
            result = {"url": url, "status": r.status_code, "bytes": len(r.content), "ok": r.status_code < 400}
        except httpx.TimeoutException:
            # 정해 둔 시간(timeout) 안에 응답이 안 오면 여기로 온다
            result = {"url": url, "error": "시간 초과"}
        except httpx.ConnectError:
            # 주소를 못 찾거나 서버에 접속 자체가 안 되면 여기로 온다
            result = {"url": url, "error": "접속 실패"}
        except httpx.HTTPError as e:
            # 위 두 경우 말고 httpx가 낸 나머지 오류. 넓은 것을 맨 마지막에 둬야 한다
            result = {"url": url, "error": type(e).__name__}
        # try 바깥이라 성공·실패 모두 걸린 시간이 기록된다 (초 → 밀리초)
        result["ms"] = round((time.perf_counter() - start) * 1000)
        return result


async def fetch_all(urls, concurrency=5, timeout=3.0):
    """URL 목록을 동시에(최대 concurrency개씩) 가져와서 결과 목록을 돌려준다."""
    # 자리가 concurrency개인 Semaphore를 '한 번만' 만들어 모든 fetch_one이 같이 쓴다
    sem = asyncio.Semaphore(concurrency)
    # 클라이언트도 한 번만 만들어 재사용한다. timeout=요청마다 기다리는 최대 초
    async with httpx.AsyncClient(timeout=timeout) as client:
        # url마다 fetch_one 작업을 만들어(*로 펼쳐서) gather로 한꺼번에 실행
        # fetch_one이 실패를 직접 잡아 결과로 돌려주므로, 하나가 실패해도 전체가 멈추지 않는다
        return await asyncio.gather(*(fetch_one(client, sem, u) for u in urls))


# 테스트용 주소 20개: 성공 12, 시간 초과 3, 서버 오류 3, 접속 실패 2
URLS = (
    ["http://localhost:8081/delay/1"] * 12  # 1초 뒤 응답
    + ["http://localhost:8081/delay/5"] * 3  # 5초 뒤 응답 → 3초 제한에 걸림
    + ["http://localhost:8081/status/500"] * 3  # 바로 500 응답
    + ["http://no-such-host.invalid"] * 2  # 없는 주소
)


def sync_fetch_all(urls, timeout=3.0):
    results = []
    with httpx.Client(timeout=timeout) as client:
        for url in urls:
            start = time.perf_counter()
            try:
                r = client.get(url)
                result = {"url": url, "status": r.status_code}
            except httpx.TimeoutException:
                result = {"url": url, "error": "시간 초과"}
            except httpx.ConnectError:
                result = {"url": url, "error": "접속 실패"}
            except httpx.HTTPError as e:
                result = {"url": url, "error": type(e).__name__}
            result["ms"] = round((time.perf_counter() - start) * 1000)
            results.append(result)
    return results


if __name__ == "__main__":
    start = time.perf_counter()
    results = asyncio.run(fetch_all(URLS))  # 비동기 세계로 들어가는 입구
    for r in results:  # 결과는 URLS에 넣은 순서대로 돌아온다
        print(r)
    errors = sum(1 for r in results if "error" in r)  # 고쳐 보기 ③: 오류 개수 세기
    print(f"성공 응답 {len(results) - errors}, 오류 {errors}")
    print(f"총 {time.perf_counter() - start:.1f}초, {len(results)}개")