(function () {
  var selectors = [
    ".jobs-description__content",
    ".jobs-box__html-content",
    "#job-details",
    "[data-testid='job-description']",
    ".job-details",
    ".job-description",
    ".jobs-description",
    "#content .job-post",
    ".posting-page .section-wrapper",
    "article"
  ];
  var node = null;
  for (var i = 0; i < selectors.length; i++) {
    node = document.querySelector(selectors[i]);
    if (node && (node.innerText || "").trim().length > 80) {
      break;
    }
    node = null;
  }
  if (!node) {
    node = document.body;
  }
  return {
    url: location.href,
    html: node ? node.innerHTML : ""
  };
})();
