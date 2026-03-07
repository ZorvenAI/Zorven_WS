import { render, screen } from '@testing-library/react'
import { FilePreview, FileAttachment } from '@/components/chat/FilePreview'

describe('FilePreview', () => {
  const baseAttachment: FileAttachment = {
    id: 1,
    file_name: 'photo.png',
    file_type: 'image',
    file_size: 204800,
    pipeline_status: 'indexed',
    asset: 10,
    thumbnail_url: null,
  }

  it('renders image thumbnail when thumbnail_url is present', () => {
    const att: FileAttachment = {
      ...baseAttachment,
      thumbnail_url: 'https://storage.example.com/photo.png?signed=true',
    }

    render(<FilePreview attachments={[att]} />)

    const img = screen.getByRole('img', { name: 'photo.png' })
    expect(img).toBeInTheDocument()
    expect(img).toHaveAttribute('src', att.thumbnail_url)
  })

  it('renders file icon when thumbnail_url is absent for image', () => {
    render(<FilePreview attachments={[baseAttachment]} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('photo.png')).toBeInTheDocument()
  })

  it('renders file icon for non-image attachment', () => {
    const att: FileAttachment = {
      ...baseAttachment,
      id: 2,
      file_name: 'report.pdf',
      file_type: 'document',
      thumbnail_url: null,
    }

    render(<FilePreview attachments={[att]} />)

    expect(screen.queryByRole('img')).not.toBeInTheDocument()
    expect(screen.getByText('report.pdf')).toBeInTheDocument()
  })

  it('opens thumbnail link in new tab', () => {
    const att: FileAttachment = {
      ...baseAttachment,
      thumbnail_url: 'https://storage.example.com/photo.png?signed=true',
    }

    render(<FilePreview attachments={[att]} />)

    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveAttribute('href', att.thumbnail_url)
  })

  it('returns null for empty attachments', () => {
    const { container } = render(<FilePreview attachments={[]} />)
    expect(container.firstChild).toBeNull()
  })
})
