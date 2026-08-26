const UPSTREAM_HOST_HEADER = "X-Forwarded-Host";
const UPSTREAM_PROTO_HEADER = "X-Forwarded-Proto";

export default {
  async fetch(request, env) {
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

    return fetch(upstreamRequest);
  },
};
