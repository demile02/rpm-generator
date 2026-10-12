/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#292524',
        primaryhover: '#44403C',
        accentink: '#FDFCF8',
        coral: '#FFB7B2',
        coralhover: '#E89B95',
        sage: '#E8EFE8',
        lavender: '#EFEDF4',
        pagebg: '#FDFCF8',
        lifted: '#F6F1E7',
        text1: '#292524',
        text2: '#78716C',
        bord: 'rgba(41,37,36,0.10)',
        galat: '#991B1B',
      },
      fontFamily: {
        // Outfit untuk semua teks.
        display: ['Outfit', 'system-ui', 'sans-serif'],
        body: ['Outfit', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
