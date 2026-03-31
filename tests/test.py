from openai import OpenAI

client = OpenAI(
    base_url='https://api-inference.modelscope.cn/v1',
    api_key='ms-318cf92b-9ca8-431c-94fb-42f73f2161fd', # ModelScope Token
)

response = client.chat.completions.create(
    model='ZhipuAI/GLM-4.7-Flash', # ModelScope Model-Id
    messages=[
        {
            'role': 'system',
            'content': 'You are a helpful assistant.'
        },
        {
            'role': 'user',
            'content': '你好'
        }
    ],
    stream=True
)

for chunk in response:
    if chunk.choices:
        print(chunk.choices[0].delta.content, end='', flush=True)