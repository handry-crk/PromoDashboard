export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#ECE4D4", bata: { DEFAULT: "#B42F27", dark: "#8E231D" }, ink: "#212121",
        tint: "#E0BFB1", blush: "#F1DCD3", line: "#D9CDB8", paper: "#F6F1E7",
        ok: "#2F6B4A", warn: "#B8741A",
      },
      fontFamily: { sans: ['"Open Sauce One"', '"Plus Jakarta Sans"', "system-ui", "sans-serif"] },
      borderRadius: { blob: "28px" },
    },
  },
  plugins: [],
};
