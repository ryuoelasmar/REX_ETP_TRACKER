/**
 * Zero-Reload Tab Navigation for Market Intelligence.
 *
 * Intercepts nav pill clicks, fetches fragment HTML via ?fragment=1,
 * swaps #tab-content, updates URL with pushState, handles back/forward.
 * Progressive enhancement: falls back to full navigation if fetch fails.
 */
(function() {
  'use strict';

  var contentEl = document.getElementById('tab-content');
  if (!contentEl) return;

  var navContainer = document.querySelector('.market-nav-pills');
  if (!navContainer) return;

  var loading = false;

  // -----------------------------------------------------------------------
  // Chart cleanup
  // -----------------------------------------------------------------------

  /**
   * Destroy all Chart.js instances on canvases within #tab-content.
   */
  function destroyCharts() {
    if (!window.Chart || !Chart.getChart) return;
    var canvases = contentEl.querySelectorAll('canvas');
    canvases.forEach(function(canvas) {
      var chart = Chart.getChart(canvas);
      if (chart) {
        try { chart.destroy(); } catch(e) { /* ignore */ }
      }
    });
  }

  // -----------------------------------------------------------------------
  // Script execution
  // -----------------------------------------------------------------------

  /**
   * Execute <script> tags within a container after fragment swap.
   *
   * Monkey-patches document.addEventListener so that DOMContentLoaded
   * callbacks fire immediately (since the DOM is already ready).
   * Inline scripts are cloned-replaced to trigger execution.
   */
  function executeScripts(container) {
    var origAdd = document.addEventListener;
    document.addEventListener = function(type, fn, opts) {
      if (type === 'DOMContentLoaded') {
        try { fn(); } catch(e) { console.error('[tabs] DOMContentLoaded handler error:', e); }
      } else {
        origAdd.call(document, type, fn, opts);
      }
    };

    var scripts = Array.from(container.querySelectorAll('script'));
    scripts.forEach(function(oldScript) {
      var newScript = document.createElement('script');
      if (oldScript.src) {
        // External script - check if already loaded
        if (!document.querySelector('script[src="' + oldScript.src + '"]')) {
          newScript.src = oldScript.src;
          document.head.appendChild(newScript);
        }
        oldScript.remove();
      } else {
        // Inline script - clone to trigger execution
        newScript.textContent = oldScript.textContent;
        oldScript.parentNode.replaceChild(newScript, oldScript);
      }
    });

    // Restore original addEventListener
    document.addEventListener = origAdd;
  }

  // -----------------------------------------------------------------------
  // Active tab highlight
  // -----------------------------------------------------------------------

  function updateActiveTab(url) {
    var pathname = url.split('?')[0];
    navContainer.querySelectorAll('a').forEach(function(link) {
      var href = link.getAttribute('href');
      link.classList.toggle('active', pathname === href);
    });
  }

  // -----------------------------------------------------------------------
  // Tab loading
  // -----------------------------------------------------------------------

  function loadTab(url, pushState) {
    if (loading) return;
    loading = true;
    contentEl.classList.add('tab-loading');

    var separator = url.indexOf('?') !== -1 ? '&' : '?';
    var fetchUrl = url + separator + 'fragment=1';

    fetch(fetchUrl)
      .then(function(resp) {
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        return resp.text();
      })
      .then(function(html) {
        // Destroy existing Chart.js instances before swapping
        destroyCharts();

        // Swap content
        contentEl.innerHTML = html;

        // Execute inline scripts (Chart.js init, etc.)
        executeScripts(contentEl);

        // Update URL
        if (pushState) {
          history.pushState({ tabUrl: url }, '', url);
        }

        // Update active pill
        updateActiveTab(url);

        // Fade-in animation
        contentEl.classList.add('tab-content-enter');
        contentEl.addEventListener('animationend', function handler() {
          contentEl.classList.remove('tab-content-enter');
          contentEl.removeEventListener('animationend', handler);
        });

        // Notify listeners (e.g. for re-init of theme-aware components)
        document.dispatchEvent(new CustomEvent('tab:loaded', { detail: { url: url } }));
      })
      .catch(function(err) {
        console.warn('[tabs] Load failed, falling back to full navigation:', err);
        window.location = url;
      })
      .finally(function() {
        loading = false;
        contentEl.classList.remove('tab-loading');
      });
  }

  // -----------------------------------------------------------------------
  // Event listeners
  // -----------------------------------------------------------------------

  // Intercept nav pill clicks (event delegation on container)
  navContainer.addEventListener('click', function(e) {
    var link = e.target.closest('a');
    if (!link || !navContainer.contains(link)) return;
    e.preventDefault();
    var url = link.getAttribute('href');
    if (url) loadTab(url, true);
  });

  // Handle back/forward navigation
  window.addEventListener('popstate', function(e) {
    if (e.state && e.state.tabUrl) {
      loadTab(e.state.tabUrl, false);
    }
  });

  // Set initial history state for the current page
  history.replaceState(
    { tabUrl: window.location.pathname + window.location.search },
    '',
    window.location.href
  );
})();
