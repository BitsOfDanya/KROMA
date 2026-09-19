import type { Map as MapLibreMap } from "maplibre-gl";

const PIXEL_RATIO = 2;

function draw(size: number, paint: (context: CanvasRenderingContext2D, size: number) => void) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.fillStyle = "#fff";
  context.strokeStyle = "#fff";
  paint(context, size);
  return context.getImageData(0, 0, size, size);
}

const ICONS: Record<string, (context: CanvasRenderingContext2D, size: number) => void> = {
  "k-square": (context, size) => {
    context.lineWidth = 4;
    context.strokeRect(size * 0.22, size * 0.22, size * 0.56, size * 0.56);
    context.fillRect(size * 0.4, size * 0.4, size * 0.2, size * 0.2);
  },
  "k-diamond": (context, size) => {
    context.lineWidth = 4;
    context.beginPath();
    context.moveTo(size / 2, size * 0.12);
    context.lineTo(size * 0.88, size / 2);
    context.lineTo(size / 2, size * 0.88);
    context.lineTo(size * 0.12, size / 2);
    context.closePath();
    context.stroke();
    context.beginPath();
    context.arc(size / 2, size / 2, size * 0.09, 0, Math.PI * 2);
    context.fill();
  },
  "k-arrow": (context, size) => {
    context.lineWidth = 4;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.beginPath();
    context.moveTo(size / 2, size * 0.85);
    context.lineTo(size / 2, size * 0.18);
    context.moveTo(size * 0.3, size * 0.38);
    context.lineTo(size / 2, size * 0.16);
    context.lineTo(size * 0.7, size * 0.38);
    context.stroke();
  },
  /** Filled wind vane: tip points to where wind blows (rotated by to_deg). */
  "k-wind": (context, size) => {
    context.lineJoin = "round";
    context.lineCap = "round";
    // shaft
    context.beginPath();
    context.moveTo(size * 0.5, size * 0.88);
    context.lineTo(size * 0.5, size * 0.38);
    context.lineWidth = 5;
    context.stroke();
    // filled arrowhead
    context.beginPath();
    context.moveTo(size * 0.5, size * 0.1);
    context.lineTo(size * 0.78, size * 0.48);
    context.lineTo(size * 0.5, size * 0.4);
    context.lineTo(size * 0.22, size * 0.48);
    context.closePath();
    context.fill();
    // small vane wing (reads as wind, not navigation pin)
    context.beginPath();
    context.moveTo(size * 0.5, size * 0.55);
    context.lineTo(size * 0.68, size * 0.68);
    context.lineTo(size * 0.5, size * 0.64);
    context.closePath();
    context.globalAlpha = 0.85;
    context.fill();
    context.globalAlpha = 1;
  },
  "k-flame": (context, size) => {
    context.lineWidth = 2.5;
    context.lineJoin = "round";
    context.beginPath();
    context.moveTo(size * 0.5, size * 0.12);
    context.bezierCurveTo(size * 0.72, size * 0.32, size * 0.78, size * 0.48, size * 0.72, size * 0.62);
    context.bezierCurveTo(size * 0.66, size * 0.82, size * 0.52, size * 0.9, size * 0.5, size * 0.9);
    context.bezierCurveTo(size * 0.48, size * 0.9, size * 0.34, size * 0.82, size * 0.28, size * 0.62);
    context.bezierCurveTo(size * 0.22, size * 0.48, size * 0.28, size * 0.32, size * 0.5, size * 0.12);
    context.closePath();
    context.fill();
    context.beginPath();
    context.moveTo(size * 0.5, size * 0.42);
    context.bezierCurveTo(size * 0.58, size * 0.52, size * 0.58, size * 0.62, size * 0.5, size * 0.72);
    context.bezierCurveTo(size * 0.42, size * 0.62, size * 0.42, size * 0.52, size * 0.5, size * 0.42);
    context.closePath();
    context.globalCompositeOperation = "destination-out";
    context.fill();
    context.globalCompositeOperation = "source-over";
  },
};

export function registerMapImages(map: MapLibreMap) {
  for (const [name, paint] of Object.entries(ICONS)) {
    if (map.hasImage(name)) continue;
    const image = draw(48, paint);
    if (image) map.addImage(name, image, { sdf: true, pixelRatio: PIXEL_RATIO });
  }
}
