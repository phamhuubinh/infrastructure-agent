export function parseConnectionQr(raw: string): { origin: string; code: string } {
  if (raw.length > 2048) throw new Error("Invalid Orion connection QR");
  const payload: unknown = JSON.parse(raw);
  if (
    !payload ||
    typeof payload !== "object" ||
    !("type" in payload) ||
    payload.type !== "orion-connect" ||
    !("version" in payload) ||
    payload.version !== 1 ||
    !("origin" in payload) ||
    typeof payload.origin !== "string" ||
    !("code" in payload) ||
    typeof payload.code !== "string" ||
    !/^orion_enroll_[A-Za-z0-9_-]{43}$/.test(payload.code)
  ) {
    throw new Error("Invalid Orion connection QR");
  }
  const url = new URL(payload.origin);
  if (
    url.protocol !== "https:" ||
    !url.hostname.endsWith(".ts.net") ||
    payload.origin !== url.origin
  ) {
    throw new Error("Invalid Orion connection QR origin");
  }
  return { origin: url.origin, code: payload.code };
}
