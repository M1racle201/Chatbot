"""VibeChatbot Streamlit UI：聊天模式 + 自主任务模式。"""

import contextlib
import io

import streamlit as st

from agent import Agent
from chat import Chat

chat_client = Chat()
agent_client = Agent(chat_client)

st.set_page_config(page_title="VibeChatbot", page_icon="💬", layout="centered")
st.title("💬 VibeChatbot")

mode = st.sidebar.radio("模式", ["聊天", "任务"])

if mode == "聊天":
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    if prompt := st.chat_input("输入消息，开始对话..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            response = st.write_stream(chat_client.stream_chat(prompt))
        st.session_state.messages.append({"role": "assistant", "content": response})

else:
    st.write("让 AI 自主完成多步任务：读取文档、检索知识库、生成文件等。")
    task = st.text_area("任务描述", placeholder="例如：读取 C:/docs/报告.pdf，总结并保存到 OUTPUT/总结.md")
    if st.button("🚀 执行任务"):
        if not task.strip():
            st.warning("请输入任务描述")
        else:
            with st.spinner("任务执行中..."):
                buffer = io.StringIO()
                with contextlib.redirect_stdout(buffer):
                    agent_client.run(task)
            st.markdown("### 执行结果")
            st.text(buffer.getvalue())
