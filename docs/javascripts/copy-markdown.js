/**
 * Copy Markdown Button Handler
 *
 * Overrides the llmstxt-md plugin's inline async copyMarkdownToClipboard()
 * with a synchronous version that works reliably across browsers.
 *
 * The plugin's async version breaks because await fetch() consumes the
 * transient user activation, causing navigator.clipboard.writeText() to
 * fail. This script pre-fetches markdown and copies synchronously via
 * execCommand, preserving the user gesture chain.
 *
 * Subscribes to MkDocs Material's document$ observable so it re-initializes
 * on every instant navigation, always overriding the plugin's inline script.
 */
(function() {
    'use strict';

    // Constants
    const FEEDBACK_DURATION_MS = 2000;
    const IOS_MAX_SELECTION = 999999;

    // Module state
    let cachedMarkdown = null;
    let fetchError = null;

    /**
     * Fetches markdown for the current page and caches it.
     */
    function prefetchMarkdown() {
        cachedMarkdown = null;
        fetchError = null;

        const currentPath = window.location.pathname;
        const mdPath = currentPath.endsWith('/')
            ? currentPath + 'index.md'
            : currentPath.replace(/\.html$/, '.md');

        fetch(mdPath)
            .then(function(response) {
                if (!response.ok) throw new Error('Not found');
                return response.text();
            })
            .then(function(text) {
                cachedMarkdown = text
                    .replace(/[\r\n]*Copy Markdown[\r\n\s]*$/i, '')
                    .replace(/\s+$/, '');
            })
            .catch(function(err) {
                fetchError = err;
                console.warn('Could not prefetch markdown:', err);
                hideButton();
            });
    }

    /**
     * Hides the copy button when markdown content is unavailable.
     */
    function hideButton() {
        var button = document.getElementById('llms-copy-button');
        if (button) {
            button.style.display = 'none';
        }
    }

    /**
     * Copies text to clipboard using execCommand.
     *
     * We use execCommand instead of navigator.clipboard.writeText() because
     * the Clipboard API requires the operation to be within a live user
     * gesture. Any preceding await (e.g. await fetch()) consumes the
     * transient activation, causing writeText() to throw. execCommand is
     * synchronous, so it works reliably when content is pre-fetched.
     *
     * @param {string} text - Text to copy to clipboard
     * @returns {boolean} Whether the copy succeeded
     */
    function copyToClipboard(text) {
        var textarea = document.createElement('textarea');
        textarea.value = text;

        textarea.style.cssText = 'position:fixed;top:0;left:0;width:2em;height:2em;padding:0;border:none;outline:none;box-shadow:none;background:transparent;';

        document.body.appendChild(textarea);

        if (/ipad|iphone/i.test(navigator.userAgent)) {
            textarea.contentEditable = true;
            textarea.readOnly = false;

            var range = document.createRange();
            range.selectNodeContents(textarea);

            var selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            textarea.setSelectionRange(0, IOS_MAX_SELECTION);
        } else {
            textarea.focus();
            textarea.select();
        }

        var success = false;
        try {
            success = document.execCommand('copy');
        } catch (err) {
            console.error('execCommand error:', err);
        }

        document.body.removeChild(textarea);
        return success;
    }

    /**
     * Shows success feedback on the button.
     * @param {HTMLElement} button - The button element
     */
    function showSuccess(button) {
        var originalHTML = button.innerHTML;
        button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polyline points="20 6 9 17 4 12"></polyline></svg>Copied!';
        button.classList.add('success');
        setTimeout(function() {
            button.innerHTML = originalHTML;
            button.classList.remove('success');
        }, FEEDBACK_DURATION_MS);
    }

    /**
     * Shows error feedback on the button.
     * @param {HTMLElement} button - The button element
     * @param {string} message - Error message to log
     */
    function showError(button, message) {
        console.error('Copy failed:', message);
        var originalHTML = button.innerHTML;
        button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>Failed';
        button.classList.add('error');
        setTimeout(function() {
            button.innerHTML = originalHTML;
            button.classList.remove('error');
        }, FEEDBACK_DURATION_MS);
    }

    /**
     * The synchronous copy handler. Assigned to window.copyMarkdownToClipboard
     * to override the plugin's broken async version.
     */
    function handleCopy() {
        var button = document.querySelector('#llms-copy-button button');
        if (!button) {
            console.warn('Copy button not found');
            return;
        }

        if (fetchError || !cachedMarkdown) {
            showError(button, 'Markdown not available');
            return;
        }

        var success = copyToClipboard(cachedMarkdown);

        if (success) {
            showSuccess(button);
        } else {
            showError(button, 'Copy failed');
        }
    }

    /**
     * Initializes the copy handler for the current page:
     * - Pre-fetches markdown content
     * - Overrides the plugin's inline async function with our sync version
     */
    function initialize() {
        prefetchMarkdown();
        window.copyMarkdownToClipboard = handleCopy;
    }

    // Initialize on first load
    initialize();

    // Re-initialize on every instant navigation (MkDocs Material)
    if (typeof document$ !== 'undefined') {
        document$.subscribe(function() {
            initialize();
        });
    }
})();
