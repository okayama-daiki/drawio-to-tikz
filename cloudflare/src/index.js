const UPSTREAM_HOST_HEADER = "X-Forwarded-Host";
const UPSTREAM_PROTO_HEADER = "X-Forwarded-Proto";
const ORIGIN_AUTH_HEADER = "X-Drawio2Tikz-Origin-Token";
const MAX_REQUEST_BYTES = 21 * 1024 * 1024;
const ALLOWED_METHODS = new Set(["GET", "HEAD", "POST"]);

export default {
  async fetch(request, env) {
    if (!ALLOWED_METHODS.has(request.method)) {
      return new Response("Method Not Allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD, POST" },
      });
    }

    const contentLength = request.headers.get("Content-Length");
    if (contentLength !== null) {
      const requestBytes = Number(contentLength);
      if (!Number.isSafeInteger(requestBytes) || requestBytes < 0) {
        return new Response("Invalid Content-Length", { status: 400 });
      }
      if (requestBytes > MAX_REQUEST_BYTES) {
        return new Response("Request Entity Too Large", { status: 413 });
      }
    }

    if (!env.ORIGIN_AUTH_TOKEN) {
      return new Response("Origin authentication is not configured", { status: 503 });
    }

    const incomingUrl = new URL(request.url);
    const upstreamUrl = new URL(env.ORIGIN_URL);

    upstreamUrl.pathname = incomingUrl.pathname;
    upstreamUrl.search = incomingUrl.search;

    const upstreamRequest = new Request(upstreamUrl, request);
    upstreamRequest.headers.set(UPSTREAM_HOST_HEADER, incomingUrl.host);
    upstreamRequest.headers.set(
      UPSTREAM_PROTO_HEADER,
      incomingUrl.protocol.replace(":", ""),
    );
    upstreamRequest.headers.set(ORIGIN_AUTH_HEADER, env.ORIGIN_AUTH_TOKEN);

    return fetch(upstreamRequest);
  },
};
