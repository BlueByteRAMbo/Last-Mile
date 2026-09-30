/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'route-base': '#05070B',
        'route-surface': '#080B10',
        'route-panel': '#0D1117',
        'route-cyan': '#38BDF8',
        'route-green': '#34D399',
        'route-amber': '#F59E0B',
        'route-red': '#F87171',
        'route-violet': '#A78BFA',
      }
    },
  },
  plugins: [],
}
