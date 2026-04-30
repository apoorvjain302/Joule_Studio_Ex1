import {
  Card,
  CardHeader,
  BusyIndicator,
  MessageStrip,
  Tag,
  FlexBox,
  Title,
  Text,
  Table,
  TableHeaderRow,
  TableHeaderCell,
  TableRow,
  TableCell,
  Panel,
  Timeline,
  TimelineItem,
  IllustratedMessage,
  ObjectStatus,
} from '@ui5/webcomponents-react'

// ── helpers ──────────────────────────────────────────────────────────────────

function parseAgentText(raw) {
  if (!raw) return null

  const text = typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2)

  // Extract verdict
  const verdictMatch = text.match(/\b(PASS|FAIL|PARTIAL[_\s]MATCH|MISMATCH)\b/)
  const verdict = verdictMatch ? verdictMatch[1].replace(/\s/, '_') : null

  // Extract confidence
  const confMatch = text.match(/confidence[:\s]+([0-9.]+)/i)
  const confidence = confMatch ? parseFloat(confMatch[1]) : null

  // Extract delivery order
  const deliveryMatch = text.match(/ODO[-\s][A-Z0-9-]+/i)
  const delivery = deliveryMatch ? deliveryMatch[0] : null

  // Extract HU IDs (HU- prefix or HU\d+)
  const huMatches = [...text.matchAll(/\b(HU[-]?[0-9A-Z]+)\b/gi)]
  const hus = [...new Set(huMatches.map((m) => m[1].toUpperCase()))]

  // Detect goods issue posted
  const giPosted = /goods issue.*post|post.*goods issue|GI.*success/i.test(text)

  // Detect correction
  const correctionDone = /correction.*success|HU.*correct|correct.*HU|unload.*load/i.test(text)

  // Detect delivery blocked
  const deliveryBlocked = /deliver.*block|block.*deliver/i.test(text)

  // Extract key lines for timeline (sentences that contain interesting keywords)
  const sentences = text
    .split(/[\n.]+/)
    .map((s) => s.trim())
    .filter(
      (s) =>
        s.length > 10 &&
        /step|detect|match|verify|block|correct|post|goods issue|HU|pallet|deliver/i.test(s)
    )
    .slice(0, 10)

  return {
    raw: text,
    verdict,
    confidence,
    delivery,
    hus,
    giPosted,
    correctionDone,
    deliveryBlocked,
    sentences,
  }
}

function verdictDesign(verdict) {
  switch (verdict) {
    case 'PASS':
      return { tagDesign: 'Positive', color: '#107e3e', icon: 'accept' }
    case 'FAIL':
    case 'MISMATCH':
      return { tagDesign: 'Negative', color: '#bb0000', icon: 'decline' }
    case 'PARTIAL_MATCH':
      return { tagDesign: 'Critical', color: '#e9730c', icon: 'warning2' }
    default:
      return { tagDesign: 'Set1', color: '#0854a0', icon: 'question-mark' }
  }
}

// ── component ─────────────────────────────────────────────────────────────────

export default function ResultPanel({ result, error, loading }) {
  if (loading) {
    return (
      <Card style={{ flex: '1 1 500px', minWidth: '400px' }}>
        <FlexBox
          justifyContent="Center"
          alignItems="Center"
          style={{ padding: '4rem' }}
        >
          <BusyIndicator active size="L" text="Agent is verifying pallet…" />
        </FlexBox>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        style={{ flex: '1 1 500px', minWidth: '400px' }}
        header={<CardHeader titleText="Verification Error" />}
      >
        <div style={{ padding: '1rem' }}>
          <MessageStrip design="Negative" hideCloseButton>
            {error}
          </MessageStrip>
        </div>
      </Card>
    )
  }

  if (!result) {
    return (
      <Card style={{ flex: '1 1 500px', minWidth: '400px' }}>
        <IllustratedMessage
          name="BeforeSearch"
          titleText="No Verification Yet"
          subtitleText="Fill in the form on the left and click Verify Pallet to start."
        />
      </Card>
    )
  }

  const parsed = parseAgentText(result)
  const { tagDesign, color, icon } = verdictDesign(parsed?.verdict)

  return (
    <Card
      style={{ flex: '1 1 500px', minWidth: '400px' }}
      header={
        <CardHeader
          titleText="Verification Result"
          subtitleText={parsed?.delivery ?? ''}
          avatar={<span style={{ fontSize: '1.5rem' }}>🔍</span>}
          action={
            parsed?.verdict && (
              <Tag design={tagDesign} icon={icon}>
                {parsed.verdict.replace('_', ' ')}
              </Tag>
            )
          }
        />
      }
    >
      <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>

        {/* ── KPI row ── */}
        {parsed?.verdict && (
          <FlexBox wrap="Wrap" style={{ gap: '1.5rem', marginBottom: '0.5rem' }}>
            <FlexBox direction="Column" alignItems="Center" style={{ gap: '0.25rem' }}>
              <Title level="H3" style={{ color }}>
                {parsed.verdict.replace('_', ' ')}
              </Title>
              <Text style={{ color: '#666', fontSize: '0.75rem' }}>Verdict</Text>
            </FlexBox>
            {parsed.confidence !== null && (
              <FlexBox direction="Column" alignItems="Center" style={{ gap: '0.25rem' }}>
                <Title level="H3">
                  {(parsed.confidence * 100).toFixed(0)}%
                </Title>
                <Text style={{ color: '#666', fontSize: '0.75rem' }}>Confidence</Text>
              </FlexBox>
            )}
            <FlexBox direction="Column" alignItems="Center" style={{ gap: '0.25rem' }}>
              <ObjectStatus
                state={parsed.giPosted ? 'Positive' : 'None'}
                icon={parsed.giPosted ? 'accept' : 'pending'}
              >
                {parsed.giPosted ? 'Posted' : 'Pending'}
              </ObjectStatus>
              <Text style={{ color: '#666', fontSize: '0.75rem' }}>Goods Issue</Text>
            </FlexBox>
            <FlexBox direction="Column" alignItems="Center" style={{ gap: '0.25rem' }}>
              <ObjectStatus
                state={parsed.deliveryBlocked ? 'Negative' : 'Positive'}
                icon={parsed.deliveryBlocked ? 'sys-cancel' : 'accept'}
              >
                {parsed.deliveryBlocked ? 'Blocked' : 'Open'}
              </ObjectStatus>
              <Text style={{ color: '#666', fontSize: '0.75rem' }}>Delivery</Text>
            </FlexBox>
          </FlexBox>
        )}

        {/* ── Detected HUs table ── */}
        {parsed?.hus?.length > 0 && (
          <Panel headerText={`Detected Handling Units (${parsed.hus.length})`} collapsed={false}>
            <Table>
              <TableHeaderRow>
                <TableHeaderCell>#</TableHeaderCell>
                <TableHeaderCell>HU ID</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
              </TableHeaderRow>
              {parsed.hus.map((hu, i) => (
                <TableRow key={hu}>
                  <TableCell>{i + 1}</TableCell>
                  <TableCell>
                    <Tag design="Set2">{hu}</Tag>
                  </TableCell>
                  <TableCell>
                    <ObjectStatus state="Information" icon="product">
                      Detected
                    </ObjectStatus>
                  </TableCell>
                </TableRow>
              ))}
            </Table>
          </Panel>
        )}

        {/* ── Actions applied ── */}
        {(parsed.correctionDone || parsed.giPosted || parsed.deliveryBlocked) && (
          <Panel headerText="Actions Applied" collapsed={false}>
            <div style={{ padding: '0.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {parsed.correctionDone && (
                <MessageStrip design="Positive" hideCloseButton>
                  ✅ HU correction applied — wrong picks cancelled and correct HUs loaded.
                </MessageStrip>
              )}
              {parsed.giPosted && (
                <MessageStrip design="Positive" hideCloseButton>
                  ✅ Goods Issue posted successfully to SAP EWM.
                </MessageStrip>
              )}
              {parsed.deliveryBlocked && (
                <MessageStrip design="Negative" hideCloseButton>
                  🚫 Delivery has been blocked due to critical mismatch.
                </MessageStrip>
              )}
            </div>
          </Panel>
        )}

        {/* ── Agent reasoning timeline ── */}
        {parsed?.sentences?.length > 0 && (
          <Panel headerText="Agent Reasoning" collapsed={true}>
            <Timeline>
              {parsed.sentences.map((s, i) => (
                <TimelineItem
                  key={i}
                  titleText={`Step ${i + 1}`}
                  subtitleText={s}
                  icon="activity-2"
                />
              ))}
            </Timeline>
          </Panel>
        )}

        {/* ── Raw agent response ── */}
        <Panel headerText="Raw Agent Response" collapsed={true}>
          <pre
            style={{
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              padding: '0.75rem',
              background: '#f4f4f4',
              borderRadius: '4px',
              maxHeight: '400px',
              overflow: 'auto',
            }}
          >
            {parsed.raw}
          </pre>
        </Panel>
      </div>
    </Card>
  )
}
