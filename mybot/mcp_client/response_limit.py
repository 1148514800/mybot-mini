"""Bound raw non-SSE bytes before httpx decoding and SDK response buffering."""
import httpx2

from .errors import HTTPTransportError

MAX_HTTP_JSON_BYTES = 2 * 1024 * 1024


class LimitedStream(httpx2.AsyncByteStream):
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit
        self.closed = False

    async def __aiter__(self):
        total = 0
        try:
            async for chunk in self.stream:
                total += len(chunk)
                if total > self.limit:
                    raise HTTPTransportError('http_response_too_large')
                yield chunk
        finally:
            await self.aclose()

    async def aclose(self):
        if not self.closed:
            self.closed = True
            await self.stream.aclose()


class ResponseLimitTransport(httpx2.AsyncBaseTransport):
    def __init__(self, inner):
        self.inner = inner

    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        # Enforce before any decoder is instantiated, including for SSE.
        if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
            await response.aclose()
            raise HTTPTransportError('http_content_encoding_refused')
        media = response.headers.get('content-type', '').split(';', 1)[0].strip().lower()
        if media != 'text/event-stream':
            response.stream = LimitedStream(response.stream, MAX_HTTP_JSON_BYTES)
        return response

    async def aclose(self):
        await self.inner.aclose()
