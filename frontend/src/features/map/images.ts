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
};

export function registerMapImages(map: MapLibreMap) {
  for (const [name, paint] of Object.entries(ICONS)) {
    if (map.hasImage(name)) continue;
    const image = draw(48, paint);
    if (image) map.addImage(name, image, { sdf: true, pixelRatio: PIXEL_RATIO });
  }
}
