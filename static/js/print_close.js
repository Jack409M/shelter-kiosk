document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".js-print-page").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });

  document.querySelectorAll(".js-close-page").forEach(function (button) {
    button.addEventListener("click", function () {
      window.close();
    });
  });
});
