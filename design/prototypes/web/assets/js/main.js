/* ПИСЬМА ПАМЯТИ — прототип. Без внешних библиотек.
   Анимации уважают prefers-reduced-motion. */
(function () {
  "use strict";
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.documentElement.classList.add("js"); // без JS секции остаются видимыми
  if (reduced) document.documentElement.classList.add("no-motion");

  /* Мягкое появление блоков при прокрутке */
  var revealEls = document.querySelectorAll(".reveal");
  if (!reduced && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  }

  /* Лайтбокс скана письма (нативный <dialog>) */
  document.querySelectorAll("[data-lightbox-open]").forEach(function (btn) {
    var dlg = document.getElementById(btn.getAttribute("data-lightbox-open"));
    if (!dlg) return;
    var img = dlg.querySelector("img");
    btn.addEventListener("click", function () {
      dlg.showModal();
      img.classList.remove("zoomed");
    });
    dlg.querySelectorAll("[data-lightbox-close]").forEach(function (c) {
      c.addEventListener("click", function () { dlg.close(); });
    });
    /* клик по подложке закрывает; клик по изображению — осторожное увеличение */
    dlg.addEventListener("click", function (e) {
      if (e.target === dlg || e.target.classList.contains("inner")) dlg.close();
    });
    img.addEventListener("click", function () {
      if (!reduced) img.classList.toggle("zoomed");
      else img.classList.toggle("zoomed"); /* и при reduced motion зум работает, но без transition */
    });
  });

  /* Разворачиваемая расшифровка */
  document.querySelectorAll("[data-transcript-toggle]").forEach(function (btn) {
    var target = document.getElementById(btn.getAttribute("data-transcript-toggle"));
    if (!target) return;
    btn.addEventListener("click", function () {
      var open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      target.hidden = open;
      btn.textContent = open ? "Показать расшифровку" : "Скрыть расшифровку";
    });
  });
})();
