(() => {
  'use strict';
  const workspace=new URLSearchParams(location.search).get('workspace')==='1';
  if(!workspace)return;
  document.body.classList.add('workspace');
  document.title='MLB MODEL · Workspace';
  window.__MODEL_WORKSPACE__={active:true,version:'1.0'};
})();
