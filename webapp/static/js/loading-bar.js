(function(){
  var bar = document.getElementById('page-progress');
  if (!bar) return;
  var running = false;

  function start() {
    if (running) return;
    running = true;
    bar.style.transition = 'none';
    bar.style.width = '0';
    bar.style.opacity = '1';
    // Force reflow before starting animation
    bar.offsetWidth;
    bar.style.transition = 'width 2s cubic-bezier(0.1,0.7,0.3,1), opacity 0.3s';
    bar.style.width = '80%';
  }

  function complete() {
    if (!running) return;
    running = false;
    bar.style.transition = 'width 0.2s ease, opacity 0.3s';
    bar.style.width = '100%';
    setTimeout(function(){
      bar.style.opacity = '0';
      setTimeout(function(){
        bar.style.transition = 'none';
        bar.style.width = '0';
      }, 300);
    }, 200);
  }

  document.addEventListener('click', function(e){
    var a = e.target.closest('a');
    if (!a) return;
    var href = a.getAttribute('href');
    if (!href || href === '#' || href.charAt(0) === '#') return;
    if (href.indexOf('javascript:') === 0) return;
    if (a.getAttribute('target') === '_blank') return;
    if (a.hasAttribute('download')) return;
    if (a.closest('.market-nav-pills')) return;
    start();
  });

  window.addEventListener('load', complete);
  window.addEventListener('popstate', complete);
})();
