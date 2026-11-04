const open='<svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">';
const icons={cart:'<path d="M3 5h6l5 25h23l7-18H11M15 30l-2 6h24"/><circle cx="17" cy="42" r="2"/><circle cx="35" cy="42" r="2"/>',
 facebook:'<path d="M29 44V26h7l1-8h-8v-4c0-3 2-4 5-4h4V3h-7c-8 0-12 4-12 12v3h-7v8h7v18Z"/>',
 tiktok:'<path d="M28 4v27a9 9 0 1 1-8-9v8a2 2 0 1 0 2 2V4Zm0 0c2 9 7 12 13 12v8c-6 0-10-2-13-6"/>',
 store:'<path d="M8 16h32l-3 27H11Zm8 0V11a8 8 0 0 1 16 0v5"/>',
 booking:'<rect x="5" y="9" width="38" height="34" rx="4"/><path d="M14 4v10M34 4v10M5 21h38M15 31l6 5 12-11"/>',
 email:'<rect x="4" y="10" width="40" height="29" rx="3"/><path d="m5 12 19 15 19-15"/>',
 external:'<path d="M27 5h16v16M43 5 20 28M20 8H6v34h34V28"/>',
 shirt:'<path d="m16 6-12 7 6 12 6-3v20h16V22l6 3 6-12-12-7c-1 5-15 5-16 0Z"/>',
 download:'<path d="M24 4v28m-10-10 10 10 10-10M7 34v9h34v-9"/>',
 heart:'<path d="M24 42 6 24C-7 10 14-4 24 13 34-4 55 10 42 24Z"/>',
 globe:'<circle cx="24" cy="24" r="20"/><ellipse cx="24" cy="24" rx="9" ry="20"/><path d="M4 24h40M8 12c9 6 23 6 32 0M8 36c9-6 23-6 32 0"/>',
 ticket:'<path d="m5 28 25-23 5 5c-4 4 3 11 7 7l4 5-25 23-5-5c4-4-3-11-7-7Z"/><path d="m27 12 4 4m0 4 4 4m0 4 3 3M14 28l9-9 6 6-9 9Z"/>',
 instagram:'<defs><linearGradient id="instagram-gradient" x1="0" y1="1" x2=".8" y2="0"><stop stop-color="#ffc540"/><stop offset=".4" stop-color="#fe3b66"/><stop offset=".75" stop-color="#b528dc"/><stop offset="1" stop-color="#6147e9"/></linearGradient></defs><rect class="instagram-base social-filled" x="2" y="2" width="44" height="44" rx="12"/><rect class="instagram-lines" x="10" y="10" width="28" height="28" rx="8"/><circle class="instagram-lines" cx="24" cy="24" r="7"/><circle fill="white" stroke="none" cx="33" cy="15" r="2"/>',
 spotify:'<circle class="spotify-base social-filled" cx="24" cy="24" r="22"/><path class="spotify-lines" d="M11 18c9-4 19-2 27 2M13 25c8-3 15-2 22 2M15 32c5-2 11-1 17 2"/>',
 youtube:'<rect class="youtube-base social-filled" x="1" y="8" width="46" height="32" rx="10"/><path class="youtube-play" d="m20 16 13 8-13 8Z"/>'
};
export function icon(key,unique=''){let content=icons[key]||icons.globe;content=content.replace('class="instagram-base social-filled"','class="instagram-base social-filled" fill="url(#instagram-gradient)"');if(unique)content=content.replaceAll('instagram-gradient','instagram-gradient-'+unique);return open+content+'</svg>';}
