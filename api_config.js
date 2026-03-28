(function () {
    const RENDER_PRIMARY_API_URL = 'https://sistema-restaurante-f87o.onrender.com';
    const RESTAURANT_SLUG = 'solar';
    const host = String(window.location.hostname || '').toLowerCase();
    const runningOnHostedFrontend =
        host.endsWith('.vercel.app')
        || host === 'foodos.com.br'
        || host === 'www.foodos.com.br'
        || host.endsWith('.foodos.com.br');
    const DEFAULT_API_URL = String(
        window.__APP_API_URL__
        || window.NEXT_PUBLIC_API_URL
        || RENDER_PRIMARY_API_URL
    ).trim();

    function readNextPublicGoogleMapsApiKey() {
        try {
            if (typeof process !== 'undefined' && process?.env?.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY) {
                return String(process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || '').trim();
            }
        } catch (_) {}

        return String(
            window.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY
            || window.__NEXT_PUBLIC_GOOGLE_MAPS_API_KEY__
            || window.__CENTRAL_GOOGLE_MAPS_API_KEY__
            || ''
        ).trim();
    }

    function normalizeGoogleMapsApiKey(value) {
        const clean = String(value || '').trim().replace(/^['"]+|['"]+$/g, '');
        if (!clean) return '';
        const normalized = clean.toLowerCase();
        if (normalized === 'null' || normalized === 'undefined') return '';
        return clean;
    }

    function isLikelyValidGoogleMapsApiKey(value) {
        const clean = normalizeGoogleMapsApiKey(value);
        if (!clean) return false;
        return /^AIza[0-9A-Za-z_-]{20,}$/.test(clean);
    }

    const CENTRAL_GOOGLE_MAPS_API_KEY = normalizeGoogleMapsApiKey(readNextPublicGoogleMapsApiKey());

    function resolveGoogleMapsApiKey(...candidates) {
        if (isLikelyValidGoogleMapsApiKey(CENTRAL_GOOGLE_MAPS_API_KEY)) {
            return CENTRAL_GOOGLE_MAPS_API_KEY;
        }

        for (const candidate of candidates) {
            const normalized = normalizeGoogleMapsApiKey(candidate);
            if (!normalized) continue;
            if (isLikelyValidGoogleMapsApiKey(normalized)) return normalized;
        }

        return normalizeGoogleMapsApiKey(CENTRAL_GOOGLE_MAPS_API_KEY);
    }

    function isLocalHost(hostname) {
        const host = String(hostname || '').toLowerCase();
        return host === 'localhost' || host === '127.0.0.1' || host === '::1';
    }

    function isPrivateNetworkHost(hostname) {
        const host = String(hostname || '').toLowerCase();
        if (!host) return false;
        if (isLocalHost(host)) return true;
        if (/^10\./.test(host)) return true;
        if (/^192\.168\./.test(host)) return true;
        if (/^172\.(1[6-9]|2\d|3[0-1])\./.test(host)) return true;
        return false;
    }

    function normalizeApiBase(value, currentOrigin, currentIsLocal) {
        const clean = String(value || '').trim().replace(/\/$/, '');
        if (!clean) return '';
        try {
            const parsed = new URL(clean);
            const candidateHost = parsed.hostname || '';
            const candidateIsLocal = isLocalHost(candidateHost);
            if (currentIsLocal && candidateIsLocal) return parsed.origin.replace(/\/$/, '');
            if (!currentIsLocal && candidateIsLocal) return '';
            return parsed.origin.replace(/\/$/, '');
        } catch {
            return '';
        }
    }

    function resolveApiBase(options) {
        const settings = options || {};
        const storageKey = settings.storageKey || 'api_base_url';
        const protocol = String(window.location.protocol || '').toLowerCase();
        const runningFromFile = protocol === 'file:';
        const safeOrigin = runningFromFile ? DEFAULT_API_URL : window.location.origin;
        const currentOrigin = String(safeOrigin || DEFAULT_API_URL).replace(/\/$/, '');
        const currentHost = window.location.hostname || '';
        const currentIsLocal = runningFromFile || isPrivateNetworkHost(currentHost);

        const fromWindow = String(window.__APP_API_URL__ || window.APP_API_URL || '').trim();
        const fromMeta = String(document.querySelector('meta[name="app-api-url"]')?.content || '').trim();
        const fromQuery = String(new URLSearchParams(window.location.search).get('api') || '').trim();
        const fromDefault = String(DEFAULT_API_URL || '').trim();

        const explicit = fromWindow || fromMeta || fromQuery || fromDefault;
        if (explicit) {
            const normalizedExplicit = normalizeApiBase(explicit, currentOrigin, currentIsLocal) || currentOrigin;
            localStorage.setItem(storageKey, normalizedExplicit);
            return normalizedExplicit;
        }

        const saved = String(localStorage.getItem(storageKey) || '').trim();
        if (saved) {
            const normalizedSaved = normalizeApiBase(saved, currentOrigin, currentIsLocal);
            if (normalizedSaved) {
                localStorage.setItem(storageKey, normalizedSaved);
                return normalizedSaved;
            }
        }

        const fallbackOrigin = normalizeApiBase(DEFAULT_API_URL, currentOrigin, currentIsLocal) || currentOrigin;
        localStorage.setItem(storageKey, fallbackOrigin);
        return fallbackOrigin;
    }

    window.__GOOGLE_MAPS_API_KEY__ = resolveGoogleMapsApiKey(
        window.__GOOGLE_MAPS_API_KEY__,
        window.APP_GOOGLE_MAPS_API_KEY,
        CENTRAL_GOOGLE_MAPS_API_KEY
    );
    window.__CENTRAL_GOOGLE_MAPS_API_KEY__ = CENTRAL_GOOGLE_MAPS_API_KEY;
    window.__RESTAURANT_SLUG__ = String(
        window.__RESTAURANT_SLUG__
        || window.APP_RESTAURANT_SLUG
        || RESTAURANT_SLUG
    ).trim().toLowerCase();
    window.getDefaultRestaurantSlug = function (...candidates) {
        for (const candidate of [...candidates, window.__RESTAURANT_SLUG__, RESTAURANT_SLUG]) {
            const slug = String(candidate || '').trim().toLowerCase();
            if (slug) return slug;
        }
        return '';
    };
    window.getGoogleMapsApiKey = function (...candidates) {
        return resolveGoogleMapsApiKey(...candidates, window.__GOOGLE_MAPS_API_KEY__, CENTRAL_GOOGLE_MAPS_API_KEY);
    };
    window.isLikelyValidGoogleMapsApiKey = isLikelyValidGoogleMapsApiKey;
    window.resolveApiBase = resolveApiBase;
})();