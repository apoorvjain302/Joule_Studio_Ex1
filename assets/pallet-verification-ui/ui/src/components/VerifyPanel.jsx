import { useState } from 'react'
import {
  Card,
  CardHeader,
  Form,
  FormGroup,
  FormItem,
  Input,
  Select,
  Option,
  Button,
  Label,
  MessageStrip,
  FlexBox,
} from '@ui5/webcomponents-react'

const SAMPLE_DELIVERIES = [
  { id: 'ODO-2024-001', label: 'ODO-2024-001 – 3 HUs, Electronics' },
  { id: 'ODO-2024-002', label: 'ODO-2024-002 – 5 HUs, Apparel' },
]

const SAMPLE_IMAGES = [
  {
    id: 'pallet_odo_001_correct.jpg',
    label: 'Correct pallet (all HUs match)',
  },
  {
    id: 'pallet_odo_001_partial.jpg',
    label: 'Partial match (1 of 3 HUs wrong)',
  },
  {
    id: 'pallet_odo_001_wrong.jpg',
    label: 'Wrong pallet (complete mismatch)',
  },
]

export default function VerifyPanel({ onVerify, loading }) {
  const [deliveryOrder, setDeliveryOrder] = useState('ODO-2024-001')
  const [imageUrl, setImageUrl] = useState('pallet_odo_001_correct.jpg')
  const [channel, setChannel] = useState('web')
  const [customDelivery, setCustomDelivery] = useState('')
  const [customImage, setCustomImage] = useState('')

  const effectiveDelivery = customDelivery || deliveryOrder
  const effectiveImage = customImage || imageUrl

  const handleSubmit = () => {
    if (!effectiveDelivery || !effectiveImage) return
    onVerify({ deliveryOrder: effectiveDelivery, imageUrl: effectiveImage, channel })
  }

  return (
    <Card
      style={{ minWidth: '360px', flex: '0 0 360px' }}
      header={
        <CardHeader
          titleText="Pallet Verification Request"
          subtitleText="Submit a pallet photo for AI verification"
          avatar={<span style={{ fontSize: '1.5rem' }}>📦</span>}
        />
      }
    >
      <div style={{ padding: '1rem' }}>
        <MessageStrip
          design="Information"
          hideCloseButton
          style={{ marginBottom: '1rem' }}
        >
          Select or type a delivery order number and provide a pallet image.
          The AI agent will detect HU labels and cross-check against live EWM
          delivery data.
        </MessageStrip>

        <Form columnsL={1} columnsM={1} columnsS={1}>
          <FormGroup headerText="Delivery">
            <FormItem label={<Label required>Delivery Order</Label>}>
              <Select
                onChange={(e) => {
                  setDeliveryOrder(e.detail.selectedOption.value)
                  setCustomDelivery('')
                }}
                style={{ width: '100%' }}
              >
                {SAMPLE_DELIVERIES.map((d) => (
                  <Option key={d.id} value={d.id}>
                    {d.label}
                  </Option>
                ))}
              </Select>
            </FormItem>
            <FormItem label={<Label>Or enter custom</Label>}>
              <Input
                placeholder="e.g. ODO-2024-099"
                value={customDelivery}
                onInput={(e) => setCustomDelivery(e.target.value)}
                style={{ width: '100%' }}
              />
            </FormItem>
          </FormGroup>

          <FormGroup headerText="Pallet Image">
            <FormItem label={<Label required>Sample Image</Label>}>
              <Select
                onChange={(e) => {
                  setImageUrl(e.detail.selectedOption.value)
                  setCustomImage('')
                }}
                style={{ width: '100%' }}
              >
                {SAMPLE_IMAGES.map((img) => (
                  <Option key={img.id} value={img.id}>
                    {img.label}
                  </Option>
                ))}
              </Select>
            </FormItem>
            <FormItem label={<Label>Or enter image URL</Label>}>
              <Input
                placeholder="https://... or base64 data URI"
                value={customImage}
                onInput={(e) => setCustomImage(e.target.value)}
                style={{ width: '100%' }}
              />
            </FormItem>
          </FormGroup>

          <FormGroup headerText="Channel">
            <FormItem label={<Label>Source channel</Label>}>
              <Select
                onChange={(e) => setChannel(e.detail.selectedOption.value)}
                style={{ width: '100%' }}
              >
                <Option value="web" selected>Web browser</Option>
                <Option value="mobile">Mobile app</Option>
                <Option value="handheld">Handheld scanner</Option>
                <Option value="dock_camera">Dock camera</Option>
              </Select>
            </FormItem>
          </FormGroup>
        </Form>

        <FlexBox justifyContent="End" style={{ marginTop: '1.5rem' }}>
          <Button
            design="Emphasized"
            icon="inspection"
            disabled={loading || (!effectiveDelivery && !customDelivery)}
            onClick={handleSubmit}
          >
            {loading ? 'Verifying…' : 'Verify Pallet'}
          </Button>
        </FlexBox>
      </div>
    </Card>
  )
}
