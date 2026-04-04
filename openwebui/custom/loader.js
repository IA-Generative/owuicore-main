// Self-bootstrap: re-inject as inline script to bypass crossorigin="use-credentials" restriction
(function(){try{
var s=document.createElement('script');
s.textContent=document.currentScript.textContent.split('/*PAYLOAD*/')[1];
document.head.appendChild(s);
}catch(e){}})();
/*PAYLOAD*/
(function () {
  "use strict";
  var _orig = Clipboard.prototype.writeText;
  Clipboard.prototype.writeText = async function (text) {
    var proseBlocks = document.querySelectorAll(".prose");
    var bestMatch = null;
    for (var i = 0; i < proseBlocks.length; i++) {
      var prose = proseBlocks[i];
      var plain = (prose.innerText || "").trim();
      if (!plain || !text || plain.length < 20 || text.length < 20) continue;
      var a = text.replace(/^#+\s*/gm, "").replace(/\*\*/g, "").substring(0, 60).trim();
      var b = plain.substring(0, 60).trim();
      if (b.indexOf(a.substring(0, 30)) !== -1 || a.indexOf(b.substring(0, 30)) !== -1) {
        bestMatch = prose;
        break;
      }
    }
    if (bestMatch) {
      var clone = bestMatch.cloneNode(true);
      var removes = clone.querySelectorAll("button, .code-block-header, .message-actions, .copy-button, .sticky");
      for (var j = 0; j < removes.length; j++) removes[j].remove();
      var cleanText = (clone.innerText || clone.textContent || "").trim();
      var cleanHtml = clone.innerHTML.trim();
      try {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/plain": new Blob([cleanText], { type: "text/plain" }),
            "text/html": new Blob([cleanHtml], { type: "text/html" }),
          }),
        ]);
        return;
      } catch (_) {
        return _orig.call(this, cleanText);
      }
    }
    return _orig.call(this, text);
  };
  navigator.clipboard.__patched = true;
})();
