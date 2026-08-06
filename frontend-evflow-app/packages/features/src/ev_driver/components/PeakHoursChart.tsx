import { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { availabilityBandLabels, createPeakHourBars, getAvailabilityBand, getJakartaDayAndHour, getLiveComparison, getLowDemandRecommendation, peakDayLabels, selectPeakHoursDay } from '../station-status/peakHoursLogic';
import type { AvailabilityState } from '../station-status/aggregateConnectorStatuses';
import type { StationLiveStatus } from '../station-status/types';

type PeakHoursChartProps = {
  availabilityState: AvailabilityState;
  peakHours: StationLiveStatus['peakHours'];
};

// One entry per availability band. `edge` is a darker shade of `fill`, drawn as
// the bar border: the amber fill only reaches about 1.9:1 against the white card
// and a bar is a graphical object that has to stay identifiable at 3:1, so the
// border, not the fill, is what carries the bar's boundary contrast.
const bandColors = {
  green: { fill: '#10A957', edge: '#0A7C40' },
  yellow: { fill: '#F0B429', edge: '#A66A00' },
  red: { fill: '#D64545', edge: '#9B1C1C' }
} as const;

export function PeakHoursChart({ availabilityState, peakHours }: PeakHoursChartProps) {
  const jakartaNow = useMemo(() => getJakartaDayAndHour(), []);
  const [selectedDay, setSelectedDay] = useState(jakartaNow.dayOfWeek);
  const [selectedHour, setSelectedHour] = useState<number | null>(null);
  const day = selectPeakHoursDay(peakHours.days, selectedDay);
  const bars = createPeakHourBars(day);
  const dayName = peakDayLabels.find((item) => item.dayOfWeek === day?.dayOfWeek)?.fullLabel ?? 'selected day';
  const comparisonHour = jakartaNow.hour;
  const currentAccent = availabilityState === 'occupied' ? '#E87500' : '#10A957';
  const selectedBar = selectedHour === null ? null : bars[selectedHour];

  // Without history every bar would be a placeholder zero. Drawing that chart
  // would read as "this station is always empty", which is a claim we cannot
  // make -- so say there is nothing to show yet instead.
  if (!peakHours.hasHistory) {
    return (
      <View style={chartStyles.section}>
        <Text style={chartStyles.title}>Peak Hours</Text>
        <View style={chartStyles.card}>
          <Text style={chartStyles.empty}>
            Not enough visits recorded here yet. Typical busy hours will appear once this station has a few weeks of history.
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={chartStyles.section}>
      <Text style={chartStyles.title}>Peak Hours</Text>
      <View style={chartStyles.card}>
        <View style={chartStyles.days}>
          {peakDayLabels.map((item) => {
            const selected = item.dayOfWeek === day?.dayOfWeek;
            return (
              <Pressable
                accessibilityLabel={`Show ${item.fullLabel} peak hours`}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                key={item.dayOfWeek}
                onPress={() => { setSelectedDay(item.dayOfWeek); setSelectedHour(null); }}
                style={chartStyles.dayTarget}
              >
                <View style={[chartStyles.dayPill, selected && chartStyles.dayPillSelected]}>
                  <Text style={[chartStyles.dayText, selected && chartStyles.dayTextSelected]}>{item.label}</Text>
                </View>
              </Pressable>
            );
          })}
        </View>
        <ScrollView
          contentContainerStyle={chartStyles.bars}
          contentOffset={{ x: Math.max(0, (jakartaNow.hour - 4) * 44), y: 0 }}
          horizontal
          showsHorizontalScrollIndicator={false}
        >
          {bars.map((bar) => {
            const current = day?.dayOfWeek === jakartaNow.dayOfWeek && bar.hour === jakartaNow.hour;
            const selected = selectedHour === bar.hour;
            const band = getAvailabilityBand(bar.occupancyPercent);
            const bandColor = bandColors[band];
            // Three signals, three separate channels, so none can overwrite
            // another: the band owns the fill, "now" owns the marker above the
            // bar plus its always-drawn bold hour label, and the tapped bar owns
            // the outline. The current hour used to take the live accent as its
            // fill, which would now read as a band colour and claim the wrong
            // availability for that hour.
            return (
              <Pressable
                accessibilityLabel={`${dayName}, ${String(bar.hour).padStart(2, '0')}:00, ${bar.occupancyPercent} percent occupied, ${availabilityBandLabels[band]}${current ? ', current hour' : ''}`}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                key={bar.hour}
                onPress={() => setSelectedHour(bar.hour)}
                style={chartStyles.barTarget}
              >
                <View style={chartStyles.barTrack}>
                  {current ? <View style={[chartStyles.currentMarker, { backgroundColor: currentAccent }]} /> : null}
                  <View style={[
                    chartStyles.barFill,
                    { backgroundColor: bandColor.fill, borderColor: bandColor.edge, height: Math.max(4, bar.occupancyPercent * 0.72) },
                    selected && chartStyles.selectedBarOutline
                  ]} />
                </View>
                <Text style={[chartStyles.hourLabel, current && chartStyles.currentHourLabel]}>
                  {bar.hour % 2 === 0 || current ? formatChartHour(bar.hour) : ''}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
        {selectedBar ? (
          <Text accessibilityLiveRegion="polite" style={chartStyles.selectedValue}>
            {String(selectedBar.hour).padStart(2, '0')}:00 · {selectedBar.occupancyPercent}% typically occupied · {availabilityBandLabels[getAvailabilityBand(selectedBar.occupancyPercent)]}
          </Text>
        ) : null}
        <View style={chartStyles.insights}>
          <View style={chartStyles.liveRow}>
            <View style={[chartStyles.liveDot, { backgroundColor: currentAccent }]} />
            <Text style={chartStyles.live}>{getLiveComparison(peakHours.currentOccupancyPercent, bars[comparisonHour].occupancyPercent, dayName)}</Text>
          </View>
          <Text style={chartStyles.recommendation}>{getLowDemandRecommendation(bars.map((bar) => bar.occupancyPercent))}</Text>
          <Text style={chartStyles.note}>Typical visits · based on the last 4 weeks</Text>
        </View>
      </View>
    </View>
  );
}

function formatChartHour(hour: number) {
  if (hour === 0) return '12a';
  if (hour === 12) return '12p';
  return hour < 12 ? `${hour}a` : `${hour - 12}p`;
}

const chartStyles = StyleSheet.create({
  section: { gap: 8, marginTop: 16 },
  title: { color: '#687378', fontSize: 10, fontWeight: '900', letterSpacing: 0.8, textTransform: 'uppercase' },
  card: { backgroundColor: '#FFFFFF', borderColor: '#E3E8E9', borderRadius: 14, borderWidth: 1, boxShadow: '0 4px 10px rgba(29, 46, 50, 0.08)', paddingBottom: 14, paddingHorizontal: 14, paddingTop: 8 },
  days: { flexDirection: 'row', justifyContent: 'space-between' },
  dayTarget: { alignItems: 'center', justifyContent: 'center', minHeight: 44, minWidth: 44 },
  dayPill: { alignItems: 'center', backgroundColor: '#ECEEEF', borderRadius: 999, justifyContent: 'center', minHeight: 24, minWidth: 39, paddingHorizontal: 7 },
  dayPillSelected: { backgroundColor: '#00696F', borderColor: '#00696F' },
  dayText: { color: '#526168', fontSize: 9, fontWeight: '900' },
  dayTextSelected: { color: '#FFFFFF' },
  bars: { alignItems: 'flex-end', minHeight: 108, paddingBottom: 2 },
  barTarget: { alignItems: 'center', justifyContent: 'flex-end', minHeight: 108, width: 44 },
  barTrack: { alignItems: 'center', height: 82, justifyContent: 'flex-end', width: 22 },
  barFill: { borderRadius: 5, borderWidth: 1, width: 26 },
  currentMarker: { borderRadius: 2, height: 4, marginBottom: 5, width: 30 },
  selectedBarOutline: { borderColor: '#00363A', borderWidth: 2 },
  hourLabel: { color: '#839095', fontSize: 8, height: 14, marginTop: 5 },
  currentHourLabel: { color: '#20272A', fontWeight: '900' },
  selectedValue: { color: '#005F64', fontSize: 10, fontWeight: '800', marginBottom: 5 },
  insights: { gap: 6, paddingTop: 5 },
  liveRow: { alignItems: 'flex-start', flexDirection: 'row', gap: 7 },
  liveDot: { borderRadius: 4, height: 7, marginTop: 4, width: 7 },
  live: { color: '#263438', flex: 1, fontSize: 10, lineHeight: 15 },
  recommendation: { color: '#465257', fontSize: 10, lineHeight: 15 },
  note: { color: '#839095', fontSize: 9, lineHeight: 14 },
  empty: { color: '#465257', fontSize: 11, lineHeight: 17 }
});
