import os
import sys
import logging
from pathlib import Path
from json import JSONDecodeError

import pandas as pd
import streamlit as st
from annotated_text import annotation
from markdown import markdown

from ui.utils import haystack_is_ready, query, send_feedback, upload_doc, haystack_version, get_backlink

import streamlit_authenticator as stauth

import yaml
from yaml.loader import SafeLoader

import requests

URL_YADISK = 'https://cloud-api.yandex.net/v1/disk/public/resources'
HEADERS_YADISK = {'Content-Type': 'application/json', 'Accept': 'application/json'}


DEFAULT_QUESTION_AT_STARTUP = os.getenv("DEFAULT_QUESTION_AT_STARTUP", "What's the capital of France?")
DEFAULT_ANSWER_AT_STARTUP = os.getenv("DEFAULT_ANSWER_AT_STARTUP", "Paris")

DEFAULT_DOCS_FROM_RETRIEVER = int(os.getenv("DEFAULT_DOCS_FROM_RETRIEVER", "3"))
DEFAULT_NUMBER_OF_ANSWERS = int(os.getenv("DEFAULT_NUMBER_OF_ANSWERS", "3"))

EVAL_LABELS = os.getenv("EVAL_FILE", str(Path(__file__).parent / "eval_labels_example.csv"))

DISABLE_FILE_UPLOAD = bool(os.getenv("DISABLE_FILE_UPLOAD"))


def set_state_if_absent(key, value):
    if key not in st.session_state:
        st.session_state[key] = value


def main():

    st.set_page_config(page_title="Askflow", page_icon="https://haystack.deepset.ai/img/HaystackIcon.png")

    set_state_if_absent("question", DEFAULT_QUESTION_AT_STARTUP)
    set_state_if_absent("answer", DEFAULT_ANSWER_AT_STARTUP)
    set_state_if_absent("results", None)
    set_state_if_absent("raw_json", None)
    set_state_if_absent("random_question_requested", False)

    def reset_results(*args):
        st.session_state.answer = None
        st.session_state.results = None
        st.session_state.raw_json = None
    path_to_config = str(Path(__file__).parent / "config.yaml")
    with open(path_to_config) as file:
        config = yaml.load(file, Loader=SafeLoader)

    authenticator = stauth.Authenticate(
        config['credentials'],
        config['cookie']['name'],
        config['cookie']['key'],
        config['cookie']['expiry_days'],
        config['preauthorized']
    )
    st.write("# Askflow MVP")
    login, register, reset_password, forgot_password = st.tabs(['Login', 'Sign up', 'Reset password', 'Forgot password'])

    with register:
        try:
            if authenticator.register_user('Register user', preauthorization=False):
                st.success('User registered successfully')
            with open(path_to_config, 'w') as file:
                yaml.dump(config, file, default_flow_style=False)
        except Exception as e:
            st.error(e)

    with login:
        name, authentication_status, username = authenticator.login('Login', 'main')  
        
        if authentication_status:
            
            authenticator.logout('Logout', 'main', key='unique_key')
            st.sidebar.header("Options")
            top_k_reader = st.sidebar.slider(
                "Max. number of answers",
                min_value=1,
                max_value=10,
                value=DEFAULT_NUMBER_OF_ANSWERS,
                step=1,
                on_change=reset_results,
            )
            top_k_retriever = st.sidebar.slider(
                "Max. number of documents from retriever",
                min_value=1,
                max_value=10,
                value=DEFAULT_DOCS_FROM_RETRIEVER,
                step=1,
                on_change=reset_results,
            )
            eval_mode = False # st.sidebar.checkbox("Evaluation mode")
            debug = False # st.sidebar.checkbox("Show debug info")

            if not DISABLE_FILE_UPLOAD:
                st.sidebar.write("## File Upload:")
                data_files = st.sidebar.file_uploader(
                    "upload", type=["pdf", "txt", "docx"], accept_multiple_files=True, label_visibility="hidden"
                )
                for data_file in data_files:
                    if data_file:
                        try:
                            raw_json = upload_doc(data_file, username)
                            st.sidebar.write(str(data_file.name) + " &nbsp;&nbsp; ✅ ")
                            if debug:
                                st.subheader("REST API JSON response")
                                st.sidebar.write(raw_json)
                        except Exception as e:
                            st.sidebar.write(str(data_file.name) + " &nbsp;&nbsp; ❌ ")
                            st.sidebar.write("This file could not be parsed")

            link_yadisk = st.sidebar.text_input('Link to your shared folder in Yandex.Disk', placeholder='https://disk.yandex.ru/d/5b4fiK7XpWMdgr')
            if not link_yadisk.startswith("https://"):
                link_yadisk = "https://" + link_yadisk
            if st.sidebar.button("Send"):
                try:
                    response_yadisk = requests.get(f'{URL_YADISK}?public_key={link_yadisk}', headers=HEADERS_YADISK).json()
                    for item in response_yadisk['_embedded']['items']:
                        if (item['mime_type'] in {'text/plain', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}):
                            yadisk_file = requests.get(item['file'])
                            try:
                                raw_json = upload_doc(yadisk_file, username)
                                st.sidebar.write(str(item['name']) + " &nbsp;&nbsp; ✅ ")
                            except Exception as e:
                                st.sidebar.write(item['name'] + " &nbsp;&nbsp; ❌ ")
                                st.sidebar.write("This file could not be parsed") 
                except Exception as e:
                    st.sidebar.write("This link is not valid ❌") 

            hs_version = ""
            try:
                hs_version = f" <small>(v{haystack_version()})</small>"
            except Exception:
                pass

            st.sidebar.markdown(
                f"""
            <style>
                a {{
                    text-decoration: none;
                }}
                .haystack-footer {{
                    text-align: center;
                }}
                .haystack-footer h4 {{
                    margin: 0.1rem;
                    padding:0;
                }}
                footer {{
                    opacity: 0;
                }}
            </style>
            <div class="haystack-footer">
                <hr />
                <h4>Project by Klukva Team</h4>
                <h4>IRIT-RTF 2023</h4>
                <hr />
            </div>
            """,
                unsafe_allow_html=True,
            )

            try:
                df = pd.read_csv(EVAL_LABELS, sep=";")
            except Exception:
                st.error(
                    f"The eval file was not found. Please check the demo's [README](https://github.com/deepset-ai/haystack/tree/main/ui/README.md) for more information."
                )
                sys.exit(
                    f"The eval file was not found under `{EVAL_LABELS}`. Please check the README (https://github.com/deepset-ai/haystack/tree/main/ui/README.md) for more information."
                )

            question = st.text_input(
                value=st.session_state.question,
                max_chars=100,
                on_change=reset_results,
                label="question",
                label_visibility="hidden",
            )
            col1, col2 = st.columns(2)
            col1.markdown("<style>.stButton button {width:100%;}</style>", unsafe_allow_html=True)
            col2.markdown("<style>.stButton button {width:100%;}</style>", unsafe_allow_html=True)

            # Run button
            run_pressed = col1.button("Run")

            # Get next random question from the CSV
            if col2.button("Random question"):
                reset_results()
                new_row = df.sample(1)
                while (
                    new_row["Question Text"].values[0] == st.session_state.question
                ):  # Avoid picking the same question twice (the change is not visible on the UI)
                    new_row = df.sample(1)
                st.session_state.question = new_row["Question Text"].values[0]
                st.session_state.answer = new_row["Answer"].values[0]
                st.session_state.random_question_requested = True
                # Re-runs the script setting the random question as the textbox value
                # Unfortunately necessary as the Random Question button is _below_ the textbox
                if hasattr(st, "scriptrunner"):
                    raise st.scriptrunner.script_runner.RerunException(
                        st.scriptrunner.script_requests.RerunData(widget_states=None)
                    )
                raise st.runtime.scriptrunner.script_runner.RerunException(
                    st.runtime.scriptrunner.script_requests.RerunData(widget_states=None)
                )
            st.session_state.random_question_requested = False

            run_query = (
                run_pressed or question != st.session_state.question
            ) and not st.session_state.random_question_requested

            # Check the connection
            with st.spinner("⌛️ &nbsp;&nbsp; Askflow is starting..."):
                if not haystack_is_ready():
                    st.error("🚫 &nbsp;&nbsp; Connection Error. Is Askflow running?")
                    run_query = False
                    reset_results()

            # Get results for query
            if run_query and question:
                reset_results()
                st.session_state.question = question

                with st.spinner(
                    "🧠 &nbsp;&nbsp; Performing neural search on documents... \n "
                ):
                    try:
                        st.session_state.results, st.session_state.raw_json = query(
                            question, top_k_reader=top_k_reader, top_k_retriever=top_k_retriever, filters={"user": username}
                        )
                    except JSONDecodeError as je:
                        st.error("👓 &nbsp;&nbsp; An error occurred reading the results. Is the document store working?")
                        return
                    except Exception as e:
                        logging.exception(e)
                        if "The server is busy processing requests" in str(e) or "503" in str(e):
                            st.error("🧑‍🌾 &nbsp;&nbsp; All our workers are busy! Try again later.")
                        else:
                            st.error("🐞 &nbsp;&nbsp; An error occurred during the request.")
                        return

            if st.session_state.results:

                # Show the gold answer if we use a question of the given set
                if eval_mode and st.session_state.answer:
                    st.write("## Correct answer:")
                    st.write(st.session_state.answer)

                st.write("## Results:")

                for count, result in enumerate(st.session_state.results):
                    if result["answer"]:
                        answer, context = result["answer"], result["context"]
                        start_idx = context.find(answer)
                        end_idx = start_idx + len(answer)
                        # Hack due to this bug: https://github.com/streamlit/streamlit/issues/3190
                        st.write(
                            markdown(context[:start_idx] + str(annotation(answer, "ANSWER", "#8ef")) + context[end_idx:]),
                            unsafe_allow_html=True,
                        )
                        source = ""
                        url, title = get_backlink(result)
                        if url and title:
                            source = f"[{result['document']['meta']['title']}]({result['document']['meta']['url']})"
                        else:
                            source = f"{result['source']}"
                        st.markdown(f"**Relevance:** {result['relevance']} -  **Source:** {source}")

                    else:
                        st.info(
                            "🤔 &nbsp;&nbsp; Askflow is unsure whether any of the documents contain an answer to your question. Try to reformulate it!"
                        )
                        st.write("**Relevance:** ", result["relevance"])

                    if eval_mode and result["answer"]:
                        # Define columns for buttons
                        is_correct_answer = None
                        is_correct_document = None

                        button_col1, button_col2, button_col3, _ = st.columns([1, 1, 1, 6])
                        if button_col1.button("👍", key=f"{result['context']}{count}1", help="Correct answer"):
                            is_correct_answer = True
                            is_correct_document = True

                        if button_col2.button("👎", key=f"{result['context']}{count}2", help="Wrong answer and wrong passage"):
                            is_correct_answer = False
                            is_correct_document = False

                        if button_col3.button(
                            "👎👍", key=f"{result['context']}{count}3", help="Wrong answer, but correct passage"
                        ):
                            is_correct_answer = False
                            is_correct_document = True

                        if is_correct_answer is not None and is_correct_document is not None:
                            try:
                                send_feedback(
                                    query=question,
                                    answer_obj=result["_raw"],
                                    is_correct_answer=is_correct_answer,
                                    is_correct_document=is_correct_document,
                                    document=result["document"],
                                )
                                st.success("✨ &nbsp;&nbsp; Thanks for your feedback! &nbsp;&nbsp; ✨")
                            except Exception as e:
                                logging.exception(e)
                                st.error("🐞 &nbsp;&nbsp; An error occurred while submitting your feedback!")

                    st.write("___")

                if debug:
                    st.subheader("REST API JSON response")
                    st.write(st.session_state.raw_json)
        elif authentication_status is False:
            st.error('Username/password is incorrect')
    
    with reset_password:
        if authentication_status:
            try:
                if authenticator.reset_password(username, 'Reset password'):
                    st.success('Password modified successfully')
                    with open(path_to_config, 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
            except Exception as e:
                st.error(e)

    with forgot_password:
        try:
            username_forgot_pw, email_forgot_password, random_password = authenticator.forgot_password('Forgot password')
            if username_forgot_pw:
                st.success('New password sent securely')
                with open(path_to_config, 'w') as file:
                    yaml.dump(config, file, default_flow_style=False)
            else:
                st.error('Username not found')
        except Exception as e:
            st.error(e)

main()
