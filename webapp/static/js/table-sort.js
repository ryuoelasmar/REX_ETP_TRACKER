/**
 * REX TABLE SORT - Unified sorting for all tables
 *
 * Replaces the duplicate sortTable() implementations in app.js and market.js.
 *
 * USAGE: No manual onclick handlers needed for new tables. Sorting is auto-
 * initialized on any <th> with class="rt-sortable" inside a .rt-table.
 *
 * SORT BEHAVIOR:
 *   - First click: descending (largest first -- most useful for financial data)
 *   - Second click: ascending
 *   - Third click: descending again
 *   - Sort indicators (arrows) appear ONLY on the active column header
 *
 * DATA TYPE DETECTION (from data-sort-type on <th>):
 *   - 'num': strips $, %, +, -, commas, B, M, K then compares as float
 *   - 'text': locale-sensitive string comparison
 *   - 'date': parses date strings for comparison
 *   - default: tries numeric, falls back to string
 *
 * CUSTOM SORT VALUE:
 *   Add data-sort="123.45" on a <td> to override the text content
 *   for sort comparison. Useful when display format differs from sort order.
 */
(function() {
  'use strict';

  function parseNum(text) {
    if (!text) return NaN;
    var cleaned = text.replace(/[$%+,BMK\s]/g, '');
    return parseFloat(cleaned);
  }

  function parseDate(text) {
    if (!text || text === '--' || text === '-') return 0;
    var d = new Date(text);
    return isNaN(d.getTime()) ? 0 : d.getTime();
  }

  function getCellValue(row, colIdx, sortType) {
    var cell = row.cells[colIdx];
    if (!cell) return '';

    var explicit = cell.getAttribute('data-sort');
    if (explicit !== null) {
      var n = parseFloat(explicit);
      return isNaN(n) ? explicit : n;
    }

    var text = cell.textContent.trim();

    if (sortType === 'num') {
      return parseNum(text);
    } else if (sortType === 'date') {
      return parseDate(text);
    } else {
      var num = parseNum(text);
      if (!isNaN(num) && text !== '') return num;
      return text;
    }
  }

  function doSort(table, colIdx, sortType) {
    var tbody = table.querySelector('tbody');
    if (!tbody) return;

    var rows = Array.from(tbody.querySelectorAll(':scope > tr:not([data-no-sort])'));

    var currentCol = table.getAttribute('data-sort-col');
    var currentDir = table.getAttribute('data-sort-dir');
    var asc;
    if (currentCol == colIdx) {
      asc = currentDir !== 'asc';
    } else {
      asc = false;
    }

    table.setAttribute('data-sort-col', colIdx);
    table.setAttribute('data-sort-dir', asc ? 'asc' : 'desc');

    rows.sort(function(a, b) {
      var aVal = getCellValue(a, colIdx, sortType);
      var bVal = getCellValue(b, colIdx, sortType);

      var aIsEmpty = (aVal === '' || (typeof aVal === 'number' && isNaN(aVal)));
      var bIsEmpty = (bVal === '' || (typeof bVal === 'number' && isNaN(bVal)));
      if (aIsEmpty && bIsEmpty) return 0;
      if (aIsEmpty) return 1;
      if (bIsEmpty) return -1;

      var result;
      if (typeof aVal === 'number' && typeof bVal === 'number') {
        result = aVal - bVal;
      } else {
        result = String(aVal).localeCompare(String(bVal));
      }
      return asc ? result : -result;
    });

    rows.forEach(function(row) { tbody.appendChild(row); });

    var allTh = table.querySelectorAll('thead th');
    allTh.forEach(function(th, i) {
      th.classList.remove('rt-sorted-asc', 'rt-sorted-desc');
      if (i === colIdx) {
        th.classList.add(asc ? 'rt-sorted-asc' : 'rt-sorted-desc');
      }
    });
  }

  function makeStickyHeaders() {
    // Apply sticky headers to all tables with sortable columns (legacy system).
    // rt-table system already has sticky via CSS, so skip those.
    document.querySelectorAll('table:not(.rt-table)').forEach(function(table) {
      var thead = table.querySelector('thead');
      if (!thead || thead.hasAttribute('data-sticky-initialized')) return;
      // Only target tables with sortable th (onclick or .sortable class)
      var hasSortable = thead.querySelector('th.sortable, th[onclick]');
      if (!hasSortable) return;
      thead.setAttribute('data-sticky-initialized', '1');
      // Tables inside .table-scroll-wrap stick to container top
      var inScrollWrap = table.closest('.table-scroll-wrap');
      thead.style.position = 'sticky';
      thead.style.top = inScrollWrap ? '0' : 'var(--nav-height, 48px)';
      thead.style.zIndex = '5';
    });
  }

  function initSortableHeaders() {
    document.querySelectorAll('.rt-table .rt-sortable').forEach(function(th) {
      if (th.hasAttribute('data-sort-initialized')) return;
      th.setAttribute('data-sort-initialized', '1');

      th.addEventListener('click', function() {
        var table = th.closest('.rt-table');
        var colIdx = parseInt(th.getAttribute('data-sort-col'));
        var sortType = th.getAttribute('data-sort-type') || 'text';
        doSort(table, colIdx, sortType);
      });
    });
    makeStickyHeaders();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSortableHeaders);
  } else {
    initSortableHeaders();
  }

  window.RexTable = {
    sort: function(tableId, colIdx, sortType) {
      var table = document.getElementById(tableId);
      if (table) doSort(table, colIdx, sortType || 'text');
    },
    init: initSortableHeaders
  };

  // Backward compat: keep global sortTable during migration
  window.sortTable = function(tableId, colIdx) {
    var table = document.getElementById(tableId);
    if (!table) return;
    doSort(table, colIdx, 'text');
    var ths = table.querySelectorAll('th');
    var dir = table.getAttribute('data-sort-dir');
    ths.forEach(function(th, i) {
      th.classList.remove('sorted-asc', 'sorted-desc');
      if (i === colIdx) {
        th.classList.add(dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
      }
    });
  };
})();
