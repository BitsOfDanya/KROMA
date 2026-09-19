import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  { ignores: ["public/**"] },
  ...nextCoreWebVitals,
  ...nextTypescript,
  { files: ["src/features/predict/PredictionResult.tsx"], rules: { "@next/next/no-img-element": "off" } },
];

export default config;
