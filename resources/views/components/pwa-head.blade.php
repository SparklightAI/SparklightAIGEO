@php
    $pwaManifestPath = \App\Support\AdminWeb::appPath('/manifest.webmanifest');
    $pwaIconPath = \App\Support\AdminWeb::appPath('/icons/sparklightaigeo-app.svg');
    $pwaAppleTouchIconPath = \App\Support\AdminWeb::appPath('/icons/sparklightaigeo-app-192.png');
@endphp
<meta name="application-name" content="SparklightAIGEO">
{{-- 星火之光AI VI：主靛蓝 #2D326B --}}
<meta name="theme-color" content="#2D326B">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="{{ $pwaManifestPath }}">
<link rel="icon" type="image/svg+xml" href="{{ $pwaIconPath }}">
<link rel="apple-touch-icon" sizes="192x192" href="{{ $pwaAppleTouchIconPath }}">
