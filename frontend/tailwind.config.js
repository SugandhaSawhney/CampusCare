/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"Public Sans"', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'] },
      colors: {
        ink: { DEFAULT: '#14213D', soft: '#3B4A66', mute: '#6B778C' },
        paper: { DEFAULT: '#F4F6F8', line: '#DDE3EA' },
        route: { DEFAULT: '#0E7C7B', dark: '#0A5E5D', tint: '#E3F2F1' },
        signal: { DEFAULT: '#B7791F', tint: '#FDF3E1' },
        breach: { DEFAULT: '#C0392B', tint: '#FBE9E7' },
        restricted: { DEFAULT: '#6D4C9F', tint: '#F0EBF7' },
      },
    },
  },
  plugins: [],
}
