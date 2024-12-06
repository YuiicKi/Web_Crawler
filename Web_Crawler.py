import os
import requests
from urllib.parse import urljoin, unquote, urlparse
from tqdm import tqdm
import socket
from requests.exceptions import RequestException
import json
import time
import random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class Downloader:
    def __init__(self, config_path='config.json'):
        """初始化下载器"""
        # 加载配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        self.session = requests.Session()
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # 从配置文件加载请求头
        self.headers = self.config['headers']
        self.base_path = self.config['base_path']
        self.save_dir = self.config['save_dir']
        
    def make_request(self, url, method="GET", data=None, stream=False, **kwargs):
        """统一的请求处理函数"""
        try:
            print(f"\n请求信息:")
            print(f"URL: {url}")
            print(f"Method: {method}")
            print(f"Headers: {json.dumps(self.headers, indent=2)}")
            if data:
                print(f"Data: {json.dumps(data, indent=2, ensure_ascii=False)}")
                
            for attempt in range(3):  # 最多重试3次
                try:
                    if method.upper() == "GET":
                        response = self.session.get(url, headers=self.headers, stream=stream, verify=False, **kwargs)
                    else:
                        response = self.session.post(url, headers=self.headers, json=data, verify=False, **kwargs)
                    
                    print(f"\n响应信息:")
                    print(f"Status Code: {response.status_code}")
                    print(f"Response Headers: {json.dumps(dict(response.headers), indent=2)}")
                    
                    # 检查响应状态
                    response.raise_for_status()
                    
                    # 尝试解析JSON响应
                    if not stream and 'application/json' in response.headers.get('Content-Type', ''):
                        try:
                            json_data = response.json()
                            print(f"Response Content: {json.dumps(json_data, indent=2, ensure_ascii=False)}")
                            if json_data.get('code') != 200:
                                raise Exception(f"API返回错误: {json_data.get('message', '未知错误')}")
                        except json.JSONDecodeError as e:
                            print(f"JSON解析错误: {str(e)}")
                            print(f"Raw Content: {response.text[:200]}...")  # 只打印前200个字符
                            raise
                    
                    return response
                    
                except requests.exceptions.RequestException as e:
                    print(f"\n请求失败 (尝试 {attempt + 1}/3):")
                    print(f"Error: {str(e)}")
                    if attempt == 2:  # 最后一次重试
                        raise
                    time.sleep(random.uniform(1, 3))  # 重试前等待
                    
        except Exception as e:
            print(f"\n请求完全失败:")
            print(f"Error Type: {type(e).__name__}")
            print(f"Error: {str(e)}")
            if isinstance(e, requests.exceptions.RequestException):
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response Status: {e.response.status_code}")
                    print(f"Response Headers: {dict(e.response.headers)}")
                    print(f"Response Content: {e.response.text[:200]}...")
            return None
            
    def download_file(self, file_info):
        """下载单个文件"""
        try:
            # 构建本地保存路径
            save_path = os.path.join(self.save_dir, file_info["dir"] if file_info["dir"] else "", file_info["name"])
            os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)

            # 检查文件是否已存在，并且大小相同
            if os.path.exists(save_path):
                if os.path.getsize(save_path) == file_info["size"]:
                    print(f"文件已存在且大小相同，跳过: {save_path}")
                    return True
                else:
                    print(f"文件已存在但大小不同，重新下载: {save_path}")

            # 检查其他可能的扩展名组合
            base_name = os.path.splitext(save_path)[0]
            possible_extensions = ['.mp4', '.MP4', '.Mp4', '.mP4']
            for ext in possible_extensions:
                alt_path = base_name + ext
                if os.path.exists(alt_path) and os.path.getsize(alt_path) == file_info["size"]:
                    print(f"文件已存在（不同扩展名）且大小相同，跳过: {alt_path}")
                    return True

            # 获取下载链接
            get_data = {
                "path": file_info["path"],
                "password": self.config['auth']['password']
            }
            
            response = self.make_request(
                urljoin(self.config['base_url'], self.config['api']['get_endpoint']),
                method="POST",
                data=get_data,
                timeout=30
            )
            
            if not response or response.status_code != 200:
                print(f"获取下载链接失败: {file_info['name']}")
                return False
                
            data = response.json()
            if data.get("code") != 200:
                print(f"获取下载链接失败: {data.get('message', '未知错误')}")
                return False
                
            download_url = data["data"]["raw_url"]
            
            # 开始下载文件
            print(f"开始下载: {file_info['name']} (大小: {file_info['size']} bytes)")
            response = self.make_request(download_url, stream=True, timeout=60)
            
            if not response or response.status_code != 200:
                print(f"下载失败: {file_info['name']}")
                return False
                
            total_size = int(response.headers.get('content-length', 0))
            
            # 创建临时文件
            temp_path = save_path + '.tmp'
            try:
                with open(temp_path, 'wb') as f, tqdm(
                    desc=file_info['name'],
                    total=total_size,
                    unit='iB',
                    unit_scale=True,
                    unit_divisor=1024,
                ) as pbar:
                    for data in response.iter_content(chunk_size=1024):
                        size = f.write(data)
                        pbar.update(size)
                
                # 下载完成后，检查文件大小
                if os.path.getsize(temp_path) == file_info["size"]:
                    # 如果文件大小正确，重命名临时文件
                    if os.path.exists(save_path):
                        os.remove(save_path)
                    os.rename(temp_path, save_path)
                    print(f"下载完成: {save_path}")
                    return True
                else:
                    print(f"下载的文件大小不正确: {file_info['name']}")
                    os.remove(temp_path)
                    return False
                    
            except Exception as e:
                print(f"写入文件时出错: {str(e)}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return False
            
        except Exception as e:
            print(f"下载文件时出错 {file_info['name']}: {str(e)}")
            return False

    def get_local_files(self):
        """获取本地已下载的文件列表"""
        local_files = set()
        for root, _, files in os.walk(self.save_dir):
            for file in files:
                if not file.endswith('.tmp'):  # 排除临时文件
                    rel_path = os.path.relpath(os.path.join(root, file), self.save_dir)
                    local_files.add(rel_path)
        return local_files

    def get_files_in_directory(self, dir_path):
        """获取目录中的文件"""
        try:
            print(f"\n获取目录内容: {dir_path}")
            
            # 构建API请求数据
            full_path = f"{self.base_path}/{dir_path}" if dir_path else self.base_path
            full_path = full_path.replace("//", "/")  # 确保没有重复的斜杠
            
            list_data = {
                "path": full_path,
                "password": self.config['auth']['password'],
                "page": 1,
                "per_page": 100,
                "refresh": False
            }
            
            print(f"请求路径: {full_path}")
            
            response = self.make_request(
                urljoin(self.config['base_url'], self.config['api']['list_endpoint']),
                method="POST",
                data=list_data,
                timeout=30
            )
            
            if response and response.status_code == 200:
                data = response.json()
                if data.get("code") == 200:
                    files = []
                    content = data["data"]["content"]
                    print(f"找到 {len(content)} 个项目")
                    
                    for item in content:
                        if item["is_dir"]:
                            print(f"\n处理子目录: {item['name']}")
                            # 处理子目录中的大小写变体
                            sub_paths = []
                            base_sub_path = f"{dir_path}/{item['name']}" if dir_path else item['name']
                            
                            # 检查目录中是否包含 'p' 或 'P'
                            if '/p' in base_sub_path.lower():
                                # 添加两种变体
                                sub_paths.append(base_sub_path)
                                sub_paths.append(base_sub_path.replace('/p', '/P'))
                                sub_paths.append(base_sub_path.replace('/P', '/p'))
                            else:
                                sub_paths.append(base_sub_path)
                            
                            # 递归处理每个变体
                            for sub_path in sub_paths:
                                print(f"尝试子路径: {sub_path}")
                                sub_files = self.get_files_in_directory(sub_path)
                                if sub_files:
                                    files.extend(sub_files)
                                    break  # 如果找到文件就不再尝试其他变体
                        else:
                            name = item["name"]
                            print(f"找到文件: {name} ({item['size']} bytes)")
                            files.append({
                                "name": name,
                                "path": f"{full_path}/{name}",
                                "size": item["size"],
                                "dir": dir_path
                            })
                    return files
                else:
                    print(f"API返回错误: {data.get('message', '未知错误')}")
            else:
                print("请求失败或返回非200状态码")
            return []
            
        except Exception as e:
            print(f"获取目录 {dir_path} 中的文件时出错: {str(e)}")
            return []
            
    def process_directory(self, dir_path=""):
        """处理目录"""
        print(f"\n开始处理目录: {dir_path or '根目录'}")
        
        # 获取本地已下载的文件列表
        local_files = self.get_local_files()
        print(f"本地已有文件数量: {len(local_files)}")
        
        # 获取目录中的所有文件（包括子目录中的文件）
        files = self.get_files_in_directory(dir_path)
        
        if not files:
            print("没有找到需要下载的文件")
            return
            
        print(f"\n找到 {len(files)} 个文件")
        
        # 下载文件
        success_count = 0
        skip_count = 0
        for file_info in files:
            # 构建相对路径用于比对
            rel_path = os.path.join(file_info["dir"] if file_info["dir"] else "", file_info["name"])
            if rel_path in local_files:
                print(f"文件已存在，跳过: {rel_path}")
                skip_count += 1
                continue
                
            if self.download_file(file_info):
                success_count += 1
                
        print(f"\n下载完成! 成功: {success_count}, 跳过: {skip_count}, 总计: {len(files)}")
            
def main():
    try:
        # 检查配置文件是否存在
        if not os.path.exists('config.json'):
            print("错误: 配置文件 'config.json' 不存在")
            print("请复制 'config.example.json' 为 'config.json' 并填入正确的配置信息")
            return

        # 加载配置
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 确保下载目录存在
        os.makedirs(config['save_dir'], exist_ok=True)
        
        # 创建下载器实例
        downloader = Downloader('config.json')
        
        # 开始下载
        print(f"开始下载到目录: {config['save_dir']}")
        downloader.process_directory()
        print("所有文件处理完成!")
        
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"发生错误: {str(e)}")

if __name__ == "__main__":
    main()
