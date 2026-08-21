import { createElement, useMemo } from 'react';

const icons = {
  bookmark: '<svg width="20" height="22" viewBox="0 0 20 22" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 1H17C18.1 1 19 1.9 19 3V20.2L10 16.2L1 20.2V3C1 1.9 1.9 1 3 1Z" stroke="#3B494A" stroke-width="2" stroke-linejoin="round"/></svg>'
};

export function BusinessPlannerIcon({ color, name }: { color: string; name: keyof typeof icons }) {
  const svg = useMemo(() => icons[name].replace(/#3B494A/g, color).replace('<svg ', '<svg style="display:block" '), [color, name]);
  return createElement('span', {
    dangerouslySetInnerHTML: { __html: svg },
    style: { alignItems: 'center', display: 'inline-flex', height: 24, justifyContent: 'center', width: 24 }
  });
}
