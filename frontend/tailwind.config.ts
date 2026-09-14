import type { Config } from "tailwindcss"

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#07090d",
        panel: "#0e1118",
        edge: "#1c2230",
        accent: "#6ee7b7",
        accent2: "#60a5fa",
      },
    },
  },
  plugins: [],
}

export default config
