/**
 * Copy Markdown Button Handler
 *
 * Pre-fetches markdown content on page load so copy is synchronous.
 * This is necessary because Safari's Clipboard API requires the copy to happen
 * synchronously within the user gesture - any async operation breaks the gesture chain.
 */
(function() {
    'use strict';

    // Constants
    const FEEDBACK_DURATION_MS = 2000;
    const IOS_MAX_SELECTION = 999999;

    // Module state
    let cachedMarkdown = null;
    let fetchError = null;

    // Fetch markdown immediately when page loads
    (function prefetchMarkdown() {
        const currentPath = window.location.pathname;
        const mdPath = currentPath.endsWith('/')
            ? currentPath + 'index.md'
            : currentPath.replace(/\.html$/, '.md');

        fetch(mdPath)
            .then(response => {
                if (!response.ok) throw new Error('Not found');
                return response.text();
            })
            .then(text => {
                // Strip any trailing "Copy Markdown" button text that the plugin may have added
                cachedMarkdown = text
                    .replace(/[\r\n]*Copy Markdown[\r\n\s]*$/i, '')
                    .replace(/\s+$/, '');
            })
            .catch(err => {
                fetchError = err;
                console.warn('Could not prefetch markdown:', err);
                // Hide the button if markdown is unavailable
                hideButton();
            });
    })();

    /**
     * Hides the copy button when markdown content is unavailable.
     */
    function hideButton() {
        const button = document.getElementById('llms-copy-button');
        if (button) {
            button.style.display = 'none';
        }
    }

    /**
     * Copies text to clipboard using execCommand.
     *
     * Note: We use execCommand instead of navigator.clipboard.writeText() because
     * Safari's Clipboard API requires operations to be synchronous within the user
     * gesture. Even with prefetched content, calling an async function (await) breaks
     * the gesture chain. By using the synchronous execCommand, we ensure reliable
     * cross-browser clipboard access including Safari/iOS.
     *
     * @param {string} text - Text to copy to clipboard
     * @returns {boolean} Whether the copy succeeded
     */
    function copyToClipboard(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;

        // Style it to be invisible but present in the DOM
        textarea.style.cssText = 'position:fixed;top:0;left:0;width:2em;height:2em;padding:0;border:none;outline:none;box-shadow:none;background:transparent;';

        document.body.appendChild(textarea);

        // Handle iOS Safari which requires special selection handling
        if (/ipad|iphone/i.test(navigator.userAgent)) {
            textarea.contentEditable = true;
            textarea.readOnly = false;

            const range = document.createRange();
            range.selectNodeContents(textarea);

            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            textarea.setSelectionRange(0, IOS_MAX_SELECTION);
        } else {
            textarea.focus();
            textarea.select();
        }

        let success = false;
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
        const originalHTML = button.innerHTML;
        button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><polyline points="20 6 9 17 4 12"></polyline></svg>Copied!';
        button.classList.add('success');
        setTimeout(() => {
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
        const originalHTML = button.innerHTML;
        button.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>Failed';
        button.classList.add('error');
        setTimeout(() => {
            button.innerHTML = originalHTML;
            button.classList.remove('error');
        }, FEEDBACK_DURATION_MS);
    }

    // Expose the copy function to window (called by plugin's onclick handler)
    window.copyMarkdownToClipboard = function() {
        const button = document.querySelector('#llms-copy-button button');
        if (!button) {
            console.warn('Copy button not found');
            return;
        }

        if (fetchError || !cachedMarkdown) {
            showError(button, 'Markdown not available');
            return;
        }

        // Synchronous copy - no async operations to preserve user gesture
        const success = copyToClipboard(cachedMarkdown);

        if (success) {
            showSuccess(button);
        } else {
            showError(button, 'Copy failed');
        }
    };
})();
