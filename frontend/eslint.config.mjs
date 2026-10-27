import nextTs from "eslint-config-next/typescript";
import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Untrusted text (requirements, AI output) must never be injected as HTML.
      "react/no-danger": "error",
    },
  },
];

export default eslintConfig;
