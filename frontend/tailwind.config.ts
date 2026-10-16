import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "agile-red": "#d7525a",
        "agile-orange": "#ebad8f",
        "agile-lightorange": "#fff6f0",
        "agile-outlinered": "#e45e5e",
        header: "#09272B",
        mainbg: "#fbf9f7",
        surface: "#ffffff",
        "secondary-text": "#64748b",
        border: "#e2e8f0",
      },
      boxShadow: {
        xs: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
      },
      borderRadius: {
        xs: "2px",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [],
};

export default config;
