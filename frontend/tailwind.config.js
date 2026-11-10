/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { 50: "#effaf8", 100: "#d5f2ec", 200: "#ade4d9", 500: "#14917f", 600: "#0f766e", 700: "#0d5f59", 900: "#0b3b38" },
        saffron: { 50: "#fff8eb", 100: "#feecc7", 400: "#f6ad3b", 500: "#ea8f12", 600: "#c76f0b" },
        ink: { 400: "#7a8794", 500: "#5b6875", 700: "#2f3a45", 900: "#141b22" },
      },
      fontFamily: { sans: ["Inter", "Segoe UI", "Nirmala UI", "Noto Sans Devanagari", "Noto Sans", "system-ui", "sans-serif"] },
      boxShadow: { card: "0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.08)" },
    },
  },
  plugins: [],
};
