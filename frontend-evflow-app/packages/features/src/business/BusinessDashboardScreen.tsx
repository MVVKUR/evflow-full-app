import { useEffect, useState } from 'react';
import { Pressable, ScrollView, Text, useWindowDimensions, View, type LayoutChangeEvent } from 'react-native';
import { useNavigate } from 'react-router';
import { clearAuthSession, fetchStats, getAuthSession } from '@evflow/shared';
import { businessDashboardStyles as styles } from '@evflow/ui';
import { useAppSafeAreaInsets } from '../shared/useAppSafeAreaInsets';
import { SvgAssetIcon } from '../shared/SvgAssetIcon';
import {
  bellIconSvg,
  buildDonutSvg,
  buildNavIconSvg,
  menuIconSvg,
  plusIconSvg,
  type BusinessNavIconName
} from './businessDashboardIcons';

const FALLBACK_STATION_TOTAL_TEXT = '480';
const FALLBACK_STATION_SOURCE = 'Source: OCM';
const LIVE_STATION_SOURCE = 'Source: PLN · OCM · OSM';
const NETWORK_UTILIZATION_PERCENT = 70;
// Estimate used only until the bottom nav reports its real height via onLayout.
const NAV_FALLBACK_HEIGHT = 90;
const NAV_ACTIVE_COLOR = '#00565F';
const NAV_INACTIVE_COLOR = '#3D494B';

type SuitabilityTierLabel = 'PRIORITY' | 'POTENTIAL' | 'SECONDARY';

type SuitabilityTag = {
  label: string;
  tone: 'teal' | 'grey';
};

type SuitabilityCandidate = {
  name: string;
  tags: SuitabilityTag[];
  score: number;
  tier: SuitabilityTierLabel;
};

const topCandidates: readonly SuitabilityCandidate[] = [
  {
    name: 'Kuningan Cyber Hub',
    tags: [{ label: 'EV: Sangat Tinggi', tone: 'teal' }, { label: 'Mall/Offices', tone: 'grey' }],
    score: 94,
    tier: 'PRIORITY'
  },
  {
    name: 'TB Simatupang Interchange',
    tags: [{ label: 'EV: Tinggi', tone: 'teal' }, { label: 'Transport Hub', tone: 'grey' }],
    score: 89,
    tier: 'PRIORITY'
  },
  {
    name: 'Sudirman Business District',
    tags: [{ label: 'EV: Sangat Tinggi', tone: 'teal' }, { label: 'Mixed Use', tone: 'grey' }],
    score: 82,
    tier: 'POTENTIAL'
  },
  {
    name: 'Kelapa Gading Commercial',
    tags: [{ label: 'EV: Sedang', tone: 'teal' }, { label: 'Residential', tone: 'grey' }],
    score: 76,
    tier: 'SECONDARY'
  }
];

const additionalCandidates: readonly SuitabilityCandidate[] = [
  {
    name: 'Summarecon Bekasi District',
    tags: [{ label: 'EV: Tinggi', tone: 'teal' }, { label: 'Mixed Use', tone: 'grey' }],
    score: 74,
    tier: 'POTENTIAL'
  },
  {
    name: 'BSD Green Office Park',
    tags: [{ label: 'EV: Tinggi', tone: 'teal' }, { label: 'Offices', tone: 'grey' }],
    score: 72,
    tier: 'POTENTIAL'
  },
  {
    name: 'Margonda Corridor Depok',
    tags: [{ label: 'EV: Sedang', tone: 'teal' }, { label: 'Retail', tone: 'grey' }],
    score: 70,
    tier: 'POTENTIAL'
  },
  {
    name: 'Sentul Toll Interchange',
    tags: [{ label: 'EV: Sedang', tone: 'teal' }, { label: 'Transport Hub', tone: 'grey' }],
    score: 67,
    tier: 'SECONDARY'
  },
  {
    name: 'Cikarang Industrial Estate',
    tags: [{ label: 'EV: Sedang', tone: 'teal' }, { label: 'Industrial', tone: 'grey' }],
    score: 65,
    tier: 'SECONDARY'
  },
  {
    name: 'Pondok Indah Mall Cluster',
    tags: [{ label: 'EV: Tinggi', tone: 'teal' }, { label: 'Mall/Offices', tone: 'grey' }],
    score: 63,
    tier: 'SECONDARY'
  },
  {
    name: 'Alam Sutera Serpong',
    tags: [{ label: 'EV: Sedang', tone: 'teal' }, { label: 'Residential', tone: 'grey' }],
    score: 61,
    tier: 'SECONDARY'
  },
  {
    name: 'Cibubur Junction Corridor',
    tags: [{ label: 'EV: Sedang', tone: 'teal' }, { label: 'Residential', tone: 'grey' }],
    score: 58,
    tier: 'SECONDARY'
  }
];

type BusinessNavItem = {
  key: BusinessNavIconName;
  label: string;
};

const navItems: readonly BusinessNavItem[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'stations', label: 'Stations' },
  { key: 'planner', label: 'Planner' },
  { key: 'customers', label: 'Customers' },
  { key: 'reports', label: 'Reports' }
];

function formatDashboardSubtitle(): string {
  const formattedDate = new Date().toLocaleDateString('id-ID', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric'
  });

  return `${formattedDate} • Jabodetabek`;
}

function getUserInitials(): string {
  const fullName = getAuthSession()?.user.full_name?.trim();

  if (!fullName) {
    return 'FO';
  }

  const initials = fullName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join('');

  return initials || 'FO';
}

export function BusinessDashboardScreen() {
  const navigate = useNavigate();
  const insets = useAppSafeAreaInsets();
  const { height } = useWindowDimensions();
  const [stationTotal, setStationTotal] = useState<number | null>(null);
  const [navHeight, setNavHeight] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;

    fetchStats()
      .then((stats) => {
        if (alive) {
          setStationTotal(stats.total);
        }
      })
      .catch((error: unknown) => {
        // Fall back silently to the static Figma value already on screen.
        console.error('Failed to load station stats', error);
      });

    return () => {
      alive = false;
    };
  }, []);

  const handleSignOut = () => {
    clearAuthSession();
    navigate('/', { replace: true });
  };

  const handleNavLayout = (event: LayoutChangeEvent) => {
    const measuredHeight = event.nativeEvent.layout.height;

    setNavHeight((current) => (current === measuredHeight ? current : measuredHeight));
  };

  const fabBottom = (navHeight ?? NAV_FALLBACK_HEIGHT + insets.bottom) + 16;

  return (
    // Bound the screen to the viewport (mirrors EVDriverContainer) so on web the
    // ScrollView scrolls internally and the bottom nav/FAB stay pinned.
    <View style={[styles.screen, { height, maxHeight: height, minHeight: height }]}>
      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        <DashboardHeader topInset={insets.top} onSignOut={handleSignOut} />

        <View style={styles.section}>
          <SummaryCards stationTotal={stationTotal} />
          <SpatialHeatmapCard />
          <Pressable
            accessibilityRole="button"
            onPress={() => navigate('/ev-driver/map')}
            style={({ pressed }) => [styles.heatmapButton, pressed && styles.pressed]}
          >
            <Text style={styles.heatmapButtonText}>View Full Heatmap & Filters  →</Text>
          </Pressable>
          <SuitabilityCard />
        </View>

        <InsightsFooter />
      </ScrollView>

      <BottomNav bottomInset={insets.bottom} onLayout={handleNavLayout} onOpenStations={() => navigate('/ev-driver/map')} />

      <Pressable
        accessibilityLabel="Open station map"
        accessibilityRole="button"
        onPress={() => navigate('/ev-driver/map')}
        style={({ pressed }) => [
          styles.fab,
          { bottom: fabBottom },
          pressed && styles.pressed
        ]}
      >
        <SvgAssetIcon height={22} svg={plusIconSvg} width={22} />
      </Pressable>
    </View>
  );
}

type DashboardHeaderProps = {
  topInset: number;
  onSignOut: () => void;
};

function DashboardHeader({ topInset, onSignOut }: DashboardHeaderProps) {
  return (
    <View style={[styles.header, { paddingTop: 16 + topInset }]}>
      <View style={styles.headerLeft}>
        <SvgAssetIcon height={22} svg={menuIconSvg} width={22} />
        <View style={styles.headerTitleGroup}>
          <Text style={styles.headerTitle}>Location Optimization</Text>
          <Text style={styles.headerSubtitle}>{formatDashboardSubtitle()}</Text>
        </View>
      </View>

      <View style={styles.headerRight}>
        <View style={styles.headerIconCircle}>
          <SvgAssetIcon height={18} svg={bellIconSvg} width={18} />
        </View>
        <Pressable
          accessibilityLabel="Sign out"
          accessibilityRole="button"
          onPress={onSignOut}
          style={({ pressed }) => [styles.headerAvatar, pressed && styles.pressed]}
        >
          <Text style={styles.headerAvatarText}>{getUserInitials()}</Text>
        </Pressable>
      </View>
    </View>
  );
}

type SummaryCardsProps = {
  stationTotal: number | null;
};

function SummaryCards({ stationTotal }: SummaryCardsProps) {
  const stationTotalText = stationTotal === null ? FALLBACK_STATION_TOTAL_TEXT : stationTotal.toLocaleString('en-US');
  const stationSourceText = stationTotal === null ? FALLBACK_STATION_SOURCE : LIVE_STATION_SOURCE;

  return (
    <View style={styles.summaryGrid}>
      <View style={[styles.card, styles.summaryCard]}>
        <Text style={styles.summaryLabel}>TOTAL EV REGISTERED</Text>
        <View style={styles.summaryValueRow}>
          <Text style={styles.summaryValue}>24,150</Text>
          <Text style={styles.summaryUnit}>Units</Text>
        </View>
        <Text style={styles.summaryFootnoteAccent}>▲ 14% Data BPS</Text>
      </View>

      <View style={[styles.card, styles.summaryCard]}>
        <Text style={styles.summaryLabel}>ACTIVE PUBLIC SPKLU</Text>
        <View style={styles.summaryValueRow}>
          <Text style={styles.summaryValue}>{stationTotalText}</Text>
          <Text style={styles.summaryUnit}>Stations</Text>
        </View>
        <Text style={styles.summaryFootnote}>{stationSourceText}</Text>
      </View>

      <View style={[styles.card, styles.summaryCard]}>
        <Text style={styles.summaryLabel}>UNMET DEMAND RATIO</Text>
        <View style={styles.summaryValueRow}>
          <Text style={[styles.summaryValue, styles.alertValue]}>3.2</Text>
          <Text style={[styles.summaryUnit, styles.alertValue]}>High Gaps</Text>
        </View>
        <View style={styles.progressRow}>
          <View style={styles.progressTrack}>
            <View style={styles.progressFill} />
          </View>
          <Text style={styles.progressCaption}>Target: &lt;1.0</Text>
        </View>
      </View>

      <View style={[styles.card, styles.summaryCard]}>
        <Text style={styles.summaryLabel}>TOP GROWTH AREA</Text>
        <Text style={styles.summaryValueSmall}>Jakarta Selatan</Text>
        <Text style={styles.summaryFootnote}>Source: Kaggle 2026</Text>
      </View>
    </View>
  );
}

function SpatialHeatmapCard() {
  return (
    <View style={[styles.card, styles.sectionCard]}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardHeaderTitle}>SPATIAL HEATMAP</Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>Jabodetabek</Text>
        </View>
      </View>

      <View style={styles.mapArea}>
        <View style={styles.mapWashLarge} />
        <View style={styles.mapWashSmall} />
        <View style={styles.mapPinLarge} />
        <View style={styles.mapPinSmall} />
        <View style={styles.mapCallout}>
          <Text style={styles.calloutEyebrow}>REKOMENDASI A</Text>
          <Text style={styles.calloutTitle}>Kuningan Cyber Hub</Text>
          <Text style={styles.calloutMeta}>Potential: 320 EVs Daily</Text>
        </View>
      </View>
    </View>
  );
}

function SuitabilityCard() {
  const [expanded, setExpanded] = useState(false);
  const visibleCandidates = expanded ? [...topCandidates, ...additionalCandidates] : topCandidates;

  return (
    <View style={[styles.card, styles.sectionCard]}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardHeaderTitle}>SITE SUITABILITY CANDIDATES</Text>
      </View>

      {visibleCandidates.map((candidate) => (
        <SuitabilityRow candidate={candidate} key={candidate.name} />
      ))}

      <View style={styles.suitabilityFooter}>
        <Pressable
          accessibilityRole="button"
          onPress={() => setExpanded((current) => !current)}
          style={({ pressed }) => [styles.suitabilityFooterButton, pressed && styles.pressed]}
        >
          <Text style={styles.suitabilityFooterText}>
            {expanded ? 'Show Top 4 Only' : 'View All 12 Recommendation Areas'}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

type SuitabilityRowProps = {
  candidate: SuitabilityCandidate;
};

function SuitabilityRow({ candidate }: SuitabilityRowProps) {
  const scoreColor = candidate.tier === 'PRIORITY' ? styles.scoreTeal : styles.scoreMuted;

  return (
    <View style={styles.suitabilityRow}>
      <View style={styles.suitabilityInfo}>
        <Text style={styles.candidateName}>{candidate.name}</Text>
        <View style={styles.tagRow}>
          {candidate.tags.map((tag) => (
            <View key={tag.label} style={tag.tone === 'teal' ? styles.tagTeal : styles.tagGrey}>
              <Text style={tag.tone === 'teal' ? styles.tagTealText : styles.tagGreyText}>{tag.label}</Text>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.scoreColumn}>
        <Text style={[styles.scoreValue, scoreColor]}>{candidate.score}%</Text>
        <Text style={[styles.scoreLabel, scoreColor]}>{candidate.tier}</Text>
      </View>
    </View>
  );
}

function InsightsFooter() {
  return (
    <View style={styles.insightsSection}>
      <View style={styles.insightBanner}>
        <Text style={styles.insightTitle}>Expansion Insight: Toll Corridor Priority</Text>
        <Text style={styles.insightBody}>
          Based on data from OCM and BPS, the East Jakarta Toll Corridor shows a 300% increase in EV passage but
          lacks ultra-fast DC chargers within a 20km radius.
        </Text>
        {/*
          Intentionally a pressed-feedback no-op: the shared downloadReceipt util is
          receipt-specific (requires ReceiptData with a transactionId) and does not
          support a generic titled report document.
        */}
        <Pressable
          accessibilityRole="button"
          style={({ pressed }) => [styles.insightButton, pressed && styles.pressed]}
        >
          <Text style={styles.insightButtonText}>Download Report</Text>
        </Pressable>
      </View>

      <View style={[styles.card, styles.utilityCard]}>
        <Text style={styles.utilityTitle}>CURRENT NETWORK UTILITY</Text>
        <View style={styles.donutWrap}>
          <SvgAssetIcon height={112} svg={buildDonutSvg(NETWORK_UTILIZATION_PERCENT)} width={112} />
          <View style={styles.donutOverlay}>
            <Text style={styles.donutValue}>{NETWORK_UTILIZATION_PERCENT}%</Text>
          </View>
        </View>
        <Text style={styles.utilityCaption}>Optimal Load Utilization</Text>
      </View>
    </View>
  );
}

type BottomNavProps = {
  bottomInset: number;
  onLayout: (event: LayoutChangeEvent) => void;
  onOpenStations: () => void;
};

function BottomNav({ bottomInset, onLayout, onOpenStations }: BottomNavProps) {
  return (
    <View onLayout={onLayout} style={[styles.bottomNav, { paddingBottom: 28 + bottomInset }]}>
      {navItems.map((item) => (
        <BottomNavItem
          active={item.key === 'planner'}
          key={item.key}
          item={item}
          onPress={item.key === 'stations' ? onOpenStations : undefined}
        />
      ))}
    </View>
  );
}

type BottomNavItemProps = {
  item: BusinessNavItem;
  active: boolean;
  onPress?: () => void;
};

function BottomNavItem({ item, active, onPress }: BottomNavItemProps) {
  const iconColor = active ? NAV_ACTIVE_COLOR : NAV_INACTIVE_COLOR;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      onPress={onPress}
      style={({ pressed }) => [styles.navItem, active && styles.navItemActive, pressed && styles.pressed]}
    >
      <SvgAssetIcon height={20} svg={buildNavIconSvg(item.key, iconColor)} width={20} />
      <Text style={[styles.navLabel, active && styles.navLabelActive]}>{item.label}</Text>
    </Pressable>
  );
}
