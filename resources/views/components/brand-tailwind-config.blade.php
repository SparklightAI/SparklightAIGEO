{{--
    星火之光AI 品牌 VI 配置（用于内置 Tailwind Play CDN 的 legacy 页面）。

    必须在引入 public/js/tailwindcss.play-cdn.js 之后渲染：CDN 会监听
    window.tailwind.config 的变化并重建样式表。颜色与 resources/css/app.css
    的 @theme 定义保持一致，两条 UI 分支（Admin UI V3 / legacy）视觉统一。
--}}
<script>
    (function () {
        var brand = {
            50: '#EFF0FA',
            100: '#DDE0F3',
            200: '#C9CCE0',
            300: '#A7ACD8',
            400: '#6F75A8',
            500: '#434A8A',
            600: '#2D326B',
            700: '#232752',
            800: '#1E2238',
            900: '#161A2C'
        };
        var coral = {
            50: '#FFF0EC',
            100: '#FFDCD3',
            200: '#FFB9A9',
            300: '#FF9280',
            400: '#FF7F6C',
            500: '#FF6B5B',
            600: '#C9473A',
            700: '#A63A2F'
        };
        var warm = {
            50: '#FBF8F4',
            100: '#F5F1EC',
            200: '#ECE9E4',
            300: '#DCD8D1',
            400: '#9A9CA8',
            500: '#6E7181',
            600: '#565A6B',
            700: '#3E4152',
            800: '#2A2D3D',
            900: '#1E2238'
        };
        var config = {
            theme: {
                extend: {
                    colors: {
                        brand: brand,
                        coral: coral,
                        warm: warm,
                        blue: brand,
                        indigo: brand,
                        gray: warm,
                        slate: warm,
                        zinc: warm,
                        neutral: warm
                    },
                    fontFamily: {
                        sans: ['Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica Neue', 'Arial', 'sans-serif']
                    },
                    borderRadius: {
                        'xl2': '16px'
                    }
                }
            }
        };

        if (window.tailwind) {
            window.tailwind.config = config;
        } else {
            window.tailwind = { config: config };
        }
    })();
</script>
