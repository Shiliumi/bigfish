// Bridge between the application panel and the native pet. It reuses the active chat.
export type PetChatStatus = 'thinking' | 'streaming' | 'complete' | 'error' | 'approval'
export function publishPetChat(status: PetChatStatus, text = '') {
  window.dispatchEvent(new CustomEvent('fish:pet-chat', { detail: { status, text } }))
  ;(window as any).webkit?.messageHandlers.fish.postMessage({ type: 'pet.chat', status, text })
}
