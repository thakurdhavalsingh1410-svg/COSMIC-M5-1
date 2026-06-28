/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Orbitron", "Inter", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        cosmic: {
          cyan: "#22d3ee",
          blue: "#2563eb",
          purple: "#a855f7",
          violet: "#7c3aed",
          night: "#030712",
          ink: "#07111f",
        },
      },
      boxShadow: {
        "cyan-glow": "0 0 28px rgba(34, 211, 238, 0.45)",
        "purple-glow": "0 0 34px rgba(168, 85, 247, 0.42)",
        "inner-cyan": "inset 0 0 30px rgba(34, 211, 238, 0.18)",
      },
      animation: {
        "slow-spin": "spin 18s linear infinite",
        float: "float 7s ease-in-out infinite",
        pulseOrb: "pulseOrb 3.8s ease-in-out infinite",
        wave: "wave 1.15s ease-in-out infinite",
        drift: "drift 18s linear infinite",
        shimmer: "shimmer 4s linear infinite",
        scan: "scan 6s ease-in-out infinite",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-14px)" },
        },
        pulseOrb: {
          "0%, 100%": {
            transform: "scale(1)",
            filter: "drop-shadow(0 0 30px rgba(34,211,238,.55))",
          },
          "50%": {
            transform: "scale(1.04)",
            filter: "drop-shadow(0 0 55px rgba(168,85,247,.78))",
          },
        },
        wave: {
          "0%, 100%": { transform: "scaleY(.35)", opacity: ".58" },
          "50%": { transform: "scaleY(1)", opacity: "1" },
        },
        drift: {
          "0%": { transform: "translate3d(0, 0, 0)" },
          "100%": { transform: "translate3d(-220px, 140px, 0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-220% 0" },
          "100%": { backgroundPosition: "220% 0" },
        },
        scan: {
          "0%, 100%": { transform: "translateY(-38%)", opacity: ".15" },
          "50%": { transform: "translateY(38%)", opacity: ".45" },
        },
      },
    },
  },
  plugins: [],
};
