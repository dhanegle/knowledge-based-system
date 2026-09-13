/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // 墨 —— 暖调中性色，取代冷灰/纯灰
        ink: {
          50: '#f8f7f4',
          100: '#f0eee9',
          200: '#e3e0d8',
          300: '#ccc7ba',
          400: '#a9a294',
          500: '#877f70',
          600: '#6a6356',
          700: '#4f4a40',
          800: '#35312b',
          900: '#201e19',
          950: '#141310',
        },
        // 朱 —— 印章色，仅用于强调（激活态、链接、焦点），不作大面积填充
        seal: {
          50: '#fcf5f2',
          100: '#f7e6df',
          200: '#efc9ba',
          300: '#e2a58d',
          400: '#cf7c5d',
          500: '#b75d3d',
          600: '#9e4b30',
          700: '#823c27',
          800: '#6a3222',
          900: '#582b1e',
        },
        // 语义色：低饱和，避免刺眼
        moss: {
          50: '#f2f5f1',
          200: '#d5e0cf',
          500: '#5f7d55',
          700: '#425a3a',
        },
        sand: {
          50: '#faf6ed',
          200: '#ecdfc6',
          500: '#a8843f',
          700: '#7c6229',
        },
        paper: '#faf9f6',
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', '"PingFang SC"',
          '"Hiragino Sans GB"', '"Microsoft YaHei"', '"Source Han Sans SC"',
          'sans-serif',
        ],
        // 衬线仅用于品牌字与标题，正文一律无衬线
        serif: [
          'Georgia', '"Songti SC"', '"SimSun"', '"Source Han Serif SC"',
          '"Noto Serif SC"', 'serif',
        ],
        mono: ['"SF Mono"', '"Cascadia Mono"', 'Consolas', '"Liberation Mono"', 'monospace'],
      },
      boxShadow: {
        hairline: '0 1px 2px rgba(20, 19, 16, 0.04)',
        pop: '0 12px 32px -8px rgba(20, 19, 16, 0.14), 0 2px 8px -3px rgba(20, 19, 16, 0.07)',
      },
      letterSpacing: {
        caps: '0.14em',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(4px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        breathe: {
          '0%, 100%': { opacity: '0.25' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        'fade-up': 'fade-up 260ms cubic-bezier(0.22, 1, 0.36, 1) both',
        breathe: 'breathe 1.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
