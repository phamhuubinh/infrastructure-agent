import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";

export function PrivateQr({ value, label }: { value: string; label: string }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const target = canvas.current;
    if (!target) return;
    let active = true;
    setFailed(false);
    void QRCode.toCanvas(target, value, { width: 264, margin: 4 }).catch(() => {
      if (active) setFailed(true);
    });
    return () => {
      active = false;
      target.getContext("2d")?.clearRect(0, 0, target.width, target.height);
    };
  }, [value]);
  return failed ? (
    <p role="alert">Không tạo được mã QR.</p>
  ) : (
    <canvas ref={canvas} aria-label={label} role="img" />
  );
}
