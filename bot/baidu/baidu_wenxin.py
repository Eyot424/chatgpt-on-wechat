# encoding:utf-8

import requests, json
from bot.bot import Bot
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf
from bot.baidu.baidu_wenxin_session import BaiduWenxinSession
from ratelimit import limits,sleep_and_retry


BAIDU_API_KEY = conf().get("baidu_wenxin_api_key")
BAIDU_SECRET_KEY = conf().get("baidu_wenxin_secret_key")

class BaiduWenxinBot(Bot):

    def __init__(self):
        super().__init__()
        self.sessions = SessionManager(BaiduWenxinSession, model=conf().get("baidu_wenxin_model") or "eb-instant")

            
    @sleep_and_retry
    @limits(calls=1, period=5)
    def reply(self, query, context=None):
        # acquire reply content
        if context and context.type:
            if context.type == ContextType.TEXT:
                logger.info("[BAIDU] query={}".format(query))
                session_id = context["session_id"]
                reply = None
                if query == "#清除记忆":
                    self.sessions.clear_session(session_id)
                    reply = Reply(ReplyType.INFO, "记忆已清除")
                elif query == "#清除所有":
                    self.sessions.clear_all_session()
                    reply = Reply(ReplyType.INFO, "所有人记忆已清除")
                elif query == '#欢迎语':
                    reply = Reply(ReplyType.TEXT, f"✨ 欢迎加入「TCDAO交易者俱乐部」！我们希望这里是大家共同交流投资方法、分享投资经验的地方，大家有任何问题都可以提出来交流哦！群里有很多我们核心成员，包括金融、互联网、Web3 及传产的高管与项目方，都是各行各业的精英，为保证社群和谐，请遵守以下规定：\n📌 请勿发布任何广告及引流信息，请勿讨论敏感内容\n📌 请勿私下添加群友\n📌 群内分析不构成任何投资建议，内容仅供参考，投资有风险，入市需谨慎\n📌 不遵守规定、恶意刷屏、言论不当的成员会被移除")
                else:
                    session = self.sessions.session_query(query, session_id)
                    result = self.reply_text(session)
                    total_tokens, completion_tokens, reply_content = (
                        result["total_tokens"],
                        result["completion_tokens"],
                        result["content"],
                    )
                    logger.debug(
                        "[BAIDU] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(session.messages, session_id, reply_content, completion_tokens)
                    )

                    if total_tokens == 0:
                        reply = Reply(ReplyType.ERROR, reply_content)
                    else:
                        self.sessions.session_reply(reply_content, session_id, total_tokens)
                        reply = Reply(ReplyType.TEXT, reply_content)
                return reply
            elif context.type == ContextType.IMAGE_CREATE:
                ok, retstring = self.create_img(query, 0)
                reply = None
                if ok:
                    reply = Reply(ReplyType.IMAGE_URL, retstring)
                else:
                    reply = Reply(ReplyType.ERROR, retstring)
                return reply
            
    def reply_text(self, session: BaiduWenxinSession, retry_count=0):
        try:
            logger.info("[BAIDU] model={}".format(session.model))
            access_token = self.get_access_token()
            if access_token == 'None':
                logger.warn("[BAIDU] access token 获取失败")
                return {
                    "total_tokens": 0,
                    "completion_tokens": 0,
                    "content": 0,
                    }
            url = "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/" + session.model + "?access_token=" + access_token
            headers = {
                'Content-Type': 'application/json'
            }
            payload = {'messages': session.messages}
            response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
            response_text = json.loads(response.text)
            logger.info(f"[BAIDU] response text={response_text}")
            res_content = response_text["result"]
            total_tokens = response_text["usage"]["total_tokens"]
            completion_tokens = response_text["usage"]["completion_tokens"]
            logger.info("[BAIDU] reply={}".format(res_content))
            return {
                "total_tokens": total_tokens,
                "completion_tokens": completion_tokens,
                "content": res_content,
            }
        except Exception as e:
            need_retry = retry_count < 2
            logger.warn("[BAIDU] Exception: {}".format(e))
            need_retry = False
            self.sessions.clear_session(session.session_id)
            result = {"completion_tokens": 0, "content": "出错了: {}".format(e)}
            return result

    def get_access_token(self):
        """
        使用 AK，SK 生成鉴权签名（Access Token）
        :return: access_token，或是None(如果错误)
        """
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {"grant_type": "client_credentials", "client_id": BAIDU_API_KEY, "client_secret": BAIDU_SECRET_KEY}
        return str(requests.post(url, params=params).json().get("access_token"))
