from chatbot.ui.ChatController import ChatController
from chatbot.dialog.DialogManager import DialogManager
from chatbot.rag.RagChain import RagChain
from chatbot.speech.SpeechToText import SpeechToText

if __name__ == "__main__":
    rag = RagChain()
    controller = ChatController(SpeechToText(), DialogManager(rag))
    controller.create_ui().launch(share=True)
