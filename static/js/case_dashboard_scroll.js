document.addEventListener("DOMContentLoaded", function () {
  const links = document.querySelectorAll(".js-scroll-link");

  links.forEach(function (link) {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      const id = link.getAttribute("href").replace("#", "");
      const el = document.getElementById(id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      }
    });
  });
});
