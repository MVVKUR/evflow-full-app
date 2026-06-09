import { createElement, useMemo } from 'react';

type SvgAssetIconProps = {
  color?: string;
  height: number;
  name?: 'bankTopup' | 'chargingFailure' | 'chargingHistory' | 'close' | 'filter' | 'leftChevron' | 'lightning' | 'rightArrow' | 'search' | 'sort' | 'tick';
  svg?: string;
  width: number;
};

const fallbackSvgs: Partial<Record<NonNullable<SvgAssetIconProps['name']>, string>> = {
  bankTopup:
    '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3 16V9H5V16H3ZM9 16V9H11V16H9ZM0 20V18H20V20H0ZM15 16V9H17V16H15ZM0 7V5L10 0L20 5V7H0ZM4.45 5H10H15.55H4.45ZM4.45 5H15.55L10 2.25L4.45 5Z" fill="#53686A"/></svg>',
  chargingFailure:
    '<svg width="22" height="19" viewBox="0 0 22 19" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M0 19L11 0L22 19H0ZM3.45 17H18.55L11 4L3.45 17ZM11 16C11.2833 16 11.5208 15.9042 11.7125 15.7125C11.9042 15.5208 12 15.2833 12 15C12 14.7167 11.9042 14.4792 11.7125 14.2875C11.5208 14.0958 11.2833 14 11 14C10.7167 14 10.4792 14.0958 10.2875 14.2875C10.0958 14.4792 10 14.7167 10 15C10 15.2833 10.0958 15.5208 10.2875 15.7125C10.4792 15.9042 10.7167 16 11 16ZM10 13H12V8H10V13Z" fill="#93000A"/></svg>',
  chargingHistory:
    '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M4.5 16L7 12H5.5V9L3 13H4.5V16ZM2 7H8V2H2V7ZM2 16H8V9H2V16ZM0 18V2C0 1.45 0.195833 0.979167 0.5875 0.5875C0.979167 0.195833 1.45 0 2 0H8C8.55 0 9.02083 0.195833 9.4125 0.5875C9.80417 0.979167 10 1.45 10 2V9H11.25C11.7333 9 12.1458 9.17083 12.4875 9.5125C12.8292 9.85417 13 10.2667 13 10.75V15.375C13 15.6583 13.1167 15.9167 13.35 16.15C13.5833 16.3833 13.8417 16.5 14.125 16.5C14.425 16.5 14.6875 16.3833 14.9125 16.15C15.1375 15.9167 15.25 15.6583 15.25 15.375V6H15C14.7167 6 14.4792 5.90417 14.2875 5.7125C14.0958 5.52083 14 5.28333 14 5V3H14.5V1.5H15.5V3H16.5V1.5H17.5V3H18V5C18 5.28333 17.9042 5.52083 17.7125 5.7125C17.5208 5.90417 17.2833 6 17 6H16.75V15.375C16.75 16.075 16.4958 16.6875 15.9875 17.2125C15.4792 17.7375 14.8583 18 14.125 18C13.4083 18 12.7917 17.7375 12.275 17.2125C11.7583 16.6875 11.5 16.075 11.5 15.375V10.75C11.5 10.6667 11.4792 10.6042 11.4375 10.5625C11.3958 10.5208 11.3333 10.5 11.25 10.5H10V18H0ZM8 16H2H8Z" fill="#53686A"/></svg>',
  close:
    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M1.4 14L0 12.6L5.6 7L0 1.4L1.4 0L7 5.6L12.6 0L14 1.4L8.4 7L14 12.6L12.6 14L7 8.4L1.4 14Z" fill="#191C1D"/></svg>',
  filter:
    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 13.5V9H7.5V10.5H13.5V12H7.5V13.5H6ZM0 12V10.5H4.5V12H0ZM3 9V7.5H0V6H3V4.5H4.5V9H3ZM6 7.5V6H13.5V7.5H6ZM9 4.5V0H10.5V1.5H13.5V3H10.5V4.5H9ZM0 3V1.5H7.5V3H0Z" fill="#3B494A"/></svg>',
  leftChevron:
    '<svg width="8" height="12" viewBox="0 0 8 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 12L0 6L6 0L7.4 1.4L2.8 6L7.4 10.6L6 12Z" fill="#191C1D"/></svg>',
  lightning:
    '<svg width="15" height="17" viewBox="0 0 15 17" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M3.33333 16.6667L6.66667 10.4167L0 9.58333L10 0H11.6667L8.33333 6.25L15 7.08333L5 16.6667H3.33333ZM7.95833 11.5208L11.3125 8.3125L5.70833 7.60417L7.02083 5.16667L3.6875 8.375L9.27083 9.0625L7.95833 11.5208Z" fill="#00696F"/></svg>',
  rightArrow:
    '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12.175 9H0V7H12.175L6.575 1.4L8 0L16 8L8 16L6.575 14.6L12.175 9Z" fill="white"/></svg>',
  search:
    '<svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M16.6 18L10.3 11.7C9.8 12.1 9.225 12.4167 8.575 12.65C7.925 12.8833 7.23333 13 6.5 13C4.68333 13 3.14583 12.3708 1.8875 11.1125C0.629167 9.85417 0 8.31667 0 6.5C0 4.68333 0.629167 3.14583 1.8875 1.8875C3.14583 0.629167 4.68333 0 6.5 0C8.31667 0 9.85417 0.629167 11.1125 1.8875C12.3708 3.14583 13 4.68333 13 6.5C13 7.23333 12.8833 7.925 12.65 8.575C12.4167 9.225 12.1 9.8 11.7 10.3L18 16.6L16.6 18ZM6.5 11C7.75 11 8.8125 10.5625 9.6875 9.6875C10.5625 8.8125 11 7.75 11 6.5C11 5.25 10.5625 4.1875 9.6875 3.3125C8.8125 2.4375 7.75 2 6.5 2C5.25 2 4.1875 2.4375 3.3125 3.3125C2.4375 4.1875 2 5.25 2 6.5C2 7.75 2.4375 8.8125 3.3125 9.6875C4.1875 10.5625 5.25 11 6.5 11Z" fill="#6B7A7B"/></svg>',
  sort:
    '<svg width="18" height="12" viewBox="0 0 18 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M7 12V10H11V12H7ZM3 7V5H15V7H3ZM0 2V0H18V2H0Z" fill="#3B494A"/></svg>',
  tick:
    '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M5.01667 8.51667L9.12917 4.40417L8.3125 3.5875L5.01667 6.88333L3.35417 5.22083L2.5375 6.0375L5.01667 8.51667ZM5.83333 11.6667C5.02639 11.6667 4.26806 11.5135 3.55833 11.2073C2.84861 10.901 2.23125 10.4854 1.70625 9.96042C1.18125 9.43542 0.765625 8.81806 0.459375 8.10833C0.153125 7.39861 0 6.64028 0 5.83333C0 5.02639 0.153125 4.26806 0.459375 3.55833C0.765625 2.84861 1.18125 2.23125 1.70625 1.70625C2.23125 1.18125 2.84861 0.765625 3.55833 0.459375C4.26806 0.153125 5.02639 0 5.83333 0C6.64028 0 7.39861 0.153125 8.10833 0.459375C8.81806 0.765625 9.43542 1.18125 9.96042 1.70625C10.4854 2.23125 10.901 2.84861 11.2073 3.55833C11.5135 4.26806 11.6667 5.02639 11.6667 5.83333C11.6667 6.64028 11.5135 7.39861 11.2073 8.10833C10.901 8.81806 10.4854 9.43542 9.96042 9.96042C9.43542 10.4854 8.81806 10.901 8.10833 11.2073C7.39861 11.5135 6.64028 11.6667 5.83333 11.6667ZM5.83333 10.5C7.13611 10.5 8.23958 10.0479 9.14375 9.14375C10.0479 8.23958 10.5 7.13611 10.5 5.83333C10.5 4.53056 10.0479 3.42708 9.14375 2.52292C8.23958 1.61875 7.13611 1.16667 5.83333 1.16667C4.53056 1.16667 3.42708 1.61875 2.52292 2.52292C1.61875 3.42708 1.16667 4.53056 1.16667 5.83333C1.16667 7.13611 1.61875 8.23958 2.52292 9.14375C3.42708 10.0479 4.53056 10.5 5.83333 10.5Z" fill="#005F64"/></svg>'
};

export function SvgAssetIcon({ color, height, name, svg, width }: SvgAssetIconProps) {
  const html = useMemo(() => {
    const sourceSvg = svg || (name ? fallbackSvgs[name] : '') || '';
    const sizedSvg = sourceSvg
      .replace(/width="[^"]*"/, `width="${width}"`)
      .replace(/height="[^"]*"/, `height="${height}"`)
      .replace('<svg ', '<svg style="display:block" ');

    return color ? sizedSvg.replace(/fill="[^"]*"/g, `fill="${color}"`) : sizedSvg;
  }, [color, height, name, svg, width]);

  return createElement('span', {
    dangerouslySetInnerHTML: { __html: html },
    style: {
      alignItems: 'center',
      display: 'inline-flex',
      height,
      justifyContent: 'center',
      width
    }
  });
}
