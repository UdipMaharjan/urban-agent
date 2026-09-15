'use client';
import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
} from 'recharts';
import type { DashboardData } from '@/lib/types';
import { Empty, Panel } from '@/components/shared/ui';
import { date, label, number } from '@/lib/utils';
const colors = { positive: '#4f806b', neutral: '#a6afb3', negative: '#bb7068', mixed: '#b99b62' };
export function SentimentChart({ data }: { data: DashboardData['sentiment'] }) {
  const values = (['positive', 'neutral', 'negative', 'mixed'] as const).map((key) => ({
    name: label(key),
    value: data[key],
    color: colors[key],
  }));
  return (
    <Panel title="Sentiment distribution" description="Validated customer feedback">
      {data.total ? (
        <div className="donut-layout">
          <div
            className="donut-chart"
            role="img"
            aria-label={values.map((v) => `${v.name}: ${v.value}`).join(', ')}
          >
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  isAnimationActive={false}
                  data={values}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="66%"
                  outerRadius="88%"
                  paddingAngle={3}
                  stroke="none"
                >
                  {values.map((v) => (
                    <Cell key={v.name} fill={v.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="donut-center">
              <strong>{number(data.total)}</strong>
              <span>validated</span>
            </div>
          </div>
          <div className="legend-list">
            {values.map((v) => (
              <div key={v.name}>
                <span>
                  <i style={{ background: v.color }} />
                  {v.name}
                </span>
                <strong>{number(v.value)}</strong>
                <small>{((v.value / data.total) * 100).toFixed(1)}%</small>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <Empty title="Sentiment is not available yet">
          Classify and validate imported feedback to see the distribution.
        </Empty>
      )}
    </Panel>
  );
}
export function CategoryChart({ data }: { data: DashboardData['categories'] }) {
  const sorted = [...data.categories].sort((a, b) => b.feedback_count - a.feedback_count);
  return (
    <Panel
      title="Feedback by category"
      description="A record can contribute to more than one category"
    >
      {data.trusted_feedback_count > 0 && sorted.length ? (
        <div
          className="chart"
          style={{ height: Math.max(240, sorted.length * 37) }}
          role="img"
          aria-label={sorted.map((x) => `${x.category}: ${x.feedback_count}`).join(', ')}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={sorted}
              layout="vertical"
              margin={{ left: 0, right: 28, top: 5, bottom: 5 }}
            >
              <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} />
              <YAxis
                dataKey="category"
                type="category"
                width={145}
                tick={{ fontSize: 11, fill: '#53635b' }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip cursor={{ fill: '#f3f6f4' }} />
              <Bar
                isAnimationActive={false}
                dataKey="feedback_count"
                name="Feedback"
                fill="#648773"
                barSize={15}
                radius={[0, 3, 3, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <Empty title="Categories will appear here">
          Validated themes reveal what customers are talking about.
        </Empty>
      )}
    </Panel>
  );
}
export function TimelineChart({ data }: { data: DashboardData['timeline'] }) {
  return (
    <Panel
      title="Sentiment over time"
      description="Weekly counts · only records with a submitted date"
    >
      {data.points.length ? (
        <>
          <div
            className="chart"
            role="img"
            aria-label={`Weekly sentiment across ${data.points.length} weeks`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data.points} margin={{ left: -25, right: 18, top: 10, bottom: 8 }}>
                <CartesianGrid vertical={false} stroke="#edf0ed" />
                <XAxis
                  dataKey="period_start"
                  tickFormatter={(v) => date(v).slice(0, 6)}
                  axisLine={false}
                  tickLine={false}
                  minTickGap={40}
                />
                <YAxis allowDecimals={false} axisLine={false} tickLine={false} />
                <Tooltip labelFormatter={(v) => date(String(v))} />
                {Object.entries(colors).map(([key, color]) => (
                  <Line
                    isAnimationActive={false}
                    key={key}
                    type="monotone"
                    dataKey={key}
                    name={label(key)}
                    stroke={color}
                    strokeWidth={2}
                    dot={data.points.length === 1 ? { r: 4 } : false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-legend">
            {Object.entries(colors).map(([key, color]) => (
              <span key={key}>
                <i style={{ background: color }} />
                {label(key)}
              </span>
            ))}
          </div>
        </>
      ) : (
        <Empty title="No dated, validated feedback">
          Time trends need submitted dates. Missing dates are never inferred.
        </Empty>
      )}
    </Panel>
  );
}
export function SeverityChart({ data }: { data: DashboardData['severity'] }) {
  const values = [
    { name: 'Low', count: data.low, color: '#648773' },
    { name: 'Medium', count: data.medium, color: '#b99b62' },
    { name: 'High', count: data.high, color: '#bb7068' },
  ];
  return (
    <Panel title="Severity distribution" description="Validated impact across customer feedback">
      {data.total ? (
        <div className="severity-bars">
          {values.map((x) => (
            <div key={x.name}>
              <div>
                <span>{x.name}</span>
                <strong>
                  {number(x.count)} <small> / {data.total}</small>
                </strong>
              </div>
              <div className="bar-track">
                <span style={{ width: `${(x.count / data.total) * 100}%`, background: x.color }} />
              </div>
            </div>
          ))}
          <p className="muted">{data.high_severity_negative} high-severity negative records</p>
        </div>
      ) : (
        <Empty title="Impact is not assessed yet">
          Severity appears after feedback has been validated.
        </Empty>
      )}
    </Panel>
  );
}
