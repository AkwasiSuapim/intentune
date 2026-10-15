import styles from './UserMessage.module.css'

type UserMessageProps = {
  text: string
}

function UserMessage({ text }: UserMessageProps) {
  return (
    <p className={styles.message}>
      <span className={styles.prefix}>You said: </span>
      {text}
    </p>
  )
}

export default UserMessage
