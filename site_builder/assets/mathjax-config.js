/* MathJax config, loaded before the vendored library.
   Inline maths arrives as \( ... \) and display maths as \[ ... \], because the
   markdown only allows round-bracket inline syntax (a bare $ is currency). */
window.MathJax = {
  tex: {
    inlineMath: [['\\(', '\\)']],
    displayMath: [['\\[', '\\]']],
    processEscapes: true,
  },
  svg: { fontCache: 'local' },
  options: {
    enableMenu: false,        // keeps the speech-rule-engine CDN path unused
    skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
  },
  startup: { typeset: true },
};
