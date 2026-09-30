/* Copyright 2026 Amon P. Lanz · SPDX-License-Identifier: Apache-2.0 */
'use strict';
(() => {
  const version='1.3.1';
  const repository='https://github.com/AmLanz/UHV-Chamber-Builder';
  const citation=`Amon P. Lanz (2026). UHV Chamber Builder (version ${version}). Computer software. Apache-2.0. ${repository}`;
  const bibtex=`@software{lanz_uhvchamberbuilder_2026,
  author = {Lanz, Amon P.},
  title = {UHV Chamber Builder},
  version = {${version}},
  year = {2026},
  license = {Apache-2.0},
  url = {${repository}},
  note = {Independent vacuum-chamber layout add-in for Autodesk Fusion}
}`;
  const box=document.querySelector('#citation-text');
  const status=document.querySelector('#copy-status');
  document.querySelector('#about-version').textContent=version;
  box.value=citation;
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-copy-citation]');
    if(!button)return;
    const bib=button.dataset.copyCitation==='bibtex';
    const text=bib?bibtex:citation;
    box.value=text;box.rows=bib?10:3;
    document.querySelector('.citation-label').textContent=bib?'BibTeX entry':'Software citation';
    status.textContent='Copying…';
    try{
      const result=await request('copy_text',{text});
      if(result.copied){status.textContent=bib?'BibTeX copied.':'Citation copied.';return;}
    }catch{} // Show selectable text when the host clipboard is unavailable.
    box.focus();box.select();
    status.textContent='Text selected. Press Ctrl+C (Windows) or Command+C (macOS) to copy.';
  });
})();
