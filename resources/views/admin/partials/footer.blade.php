@php
    $authorUrl = 'https://sparklight-ai.com';
    $footerLinkClass = 'inline-flex min-h-10 touch-manipulation items-center rounded-sm text-gray-600 underline-offset-4 transition-[color,transform] duration-150 ease-out [@media(hover:hover)]:hover:text-blue-600 [@media(hover:hover)]:hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/30 active:scale-[0.96]';
@endphp
<footer class="mt-auto shrink-0 border-t border-gray-200 bg-gray-50 text-xs leading-5 text-gray-500" data-admin-product-footer>
    <div class="mx-auto flex min-h-[52px] max-w-7xl flex-col items-start justify-center gap-x-8 px-4 py-2 sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-12">
        <div class="flex flex-wrap items-center gap-x-2" aria-label="SparklightAIGEO release information">
            <span>SparklightAIGEO v3</span>
            <span class="text-gray-300" aria-hidden="true">·</span>
            <span>{{ __('admin.footer.author_label') }}</span><a href="{{ $authorUrl }}" target="_blank" rel="noopener noreferrer" class="{{ $footerLinkClass }}">{{ __('admin.footer.author_name') }}</a>
        </div>
        <nav class="flex flex-wrap items-center gap-x-2" aria-label="SparklightAIGEO project resources">
            <button type="button" data-open-admin-welcome class="border-0 bg-transparent p-0 {{ $footerLinkClass }}">
                {{ __('admin.footer.project_intro_link') }}
            </button>
        </nav>
    </div>
</footer>
