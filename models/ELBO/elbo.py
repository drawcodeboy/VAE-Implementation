import torch
from torch import nn
import torch.distributions as dist
import torch.nn.functional as F

class ELBO(nn.Module):
    '''
        Evidence Lower Bound
        - Evidence를 실제로 구하는 것은 어렵다. -> 고차원 벡터에 대한 적분 문제
        - Evidence의 Likelihood를 maximize하여, 근사한 분포를 찾는 것을 목적으로 한다.
        - 그래서, 수식을 다르게 전개하여 ELBO + KL을 얻는데, 이 때 KL은 구하지 못 한다.
        - 왜냐하면, 해당 KL에는 True Posterior(p(z|x))이 있어서 구하지 못 한다.
        - 하지만, KL이 항상 0이상의 값을 가진다는 것은 알기 때문에 이 점을 고려하여
        - ELBO를 최대화시키는 것을 목적으로 한다.
        
        (1st Term, Regularization Term)
        이 ELBO는 -KL(q(z|x)||p(z)) + E[log p(x|z)]이며, 첫 번째 term은 
        Approximate Posterior(q(z|x))를 update시켜 Prior(p(z))와 유사하게 만들겠다는 의미이다.
        Prior과 유사하게 만드는 이유는 Posterior이 특정 데이터 x에 과하게 의존하지 않도록 하기 위함이다.
        즉, 잠재 공간의 일반화(과적합 방지)를 수행하려는 목적이 있다. 
        -> 이런 수식을 통해 '잠재 공간은 N(0, 1)에서 샘플링 된다'의 의도를 가지는 것을 알 수 있고,
        이에 따라 Gaussian에서 랜덤으로 샘플링한 Vector를 디코더에 넣으면, 새로운 데이터가 생성된다.
        
        그래서, Regularization term이라고도 불린다.
        
        (2nd Term, Reconstruction Term)
        두 번째 term은 E[log p(x|z)]로 이 Expectation을 실제로 계산할 수는 없다.
        왜냐하면, z에 대한 기댓값이라 z에 대해 적분을 해야 한다는 의미인데, 이는 Evidence를 못 구하는 것과
        같이 기댓값을 구하면 안 된다. 그래서, Monte-Carlo estimation을 통해 기댓값(가중 평균)이 아닌 평균으로
        계산을 한다. 이는 큰 수의 법칙에 의해 그렇게 정리가 가능하다.
        -(1/N)*sum^{N}(log p(x|z))
        그렇다면, 이 term이 의미하는 바는 실제 데이터가 주어졌을 때, 해당 확률 분포일 확률을 의미하는
        log-likelihood가 되고, 이를 최대화시킨다는 것은 NLL을 구한다는 것과 같다.
        그래서, 실제 데이터와 예측 데이터(확률)의 차이를 구하게 되기 때문에 Reconstruction term이라 불린다.
        
        허나, 이를 계산하는 코드에서 Binary Cross Entropy가 나온 것이 뜬금 없게 느껴질 수도 있다.
        하지만, 생각해보라. x의 각 픽셀은 모두 [0, 1]범위를 갖는 분포에서 값이 나오게 된다.
        근사적으로 접근해보면 이는 베르누이 분포라 볼 수도 있다. 그러면, 베르누이 분포의 함수 
        p^{x}(1-p)^{1-x}로 정의가 되어있고, 이의 Likelihood를 계산하기 위해 log를 씌우면
        xlogp+(1-x)log(1-p)로 이는 -BCE와 정확히 같다.
    '''
    def __init__(self, latent_size=10):
        super().__init__()
        self.latent_size = latent_size
    
    def forward(self, x_prime, x, mu, std):
        '''
            x_prime: predict
            x: target
            mu: q(z|x)의 평균
            std: q(z|x)의 표준편차
        '''
        
        # 1. Regularization Term
        prior_mu, prior_std = torch.zeros(self.latent_size).to(mu.device), torch.ones(self.latent_size).to(mu.device)
        prior = dist.Normal(prior_mu, prior_std) # p(z)
        variational = dist.Normal(mu, std) # q(z|x)
        first_term = dist.kl_divergence(variational, prior).sum() # args 순서 중요
        first_term /= x.shape[0]
        
        # 2. Reconstruction Term
        second_term = F.binary_cross_entropy(x_prime, x, reduction='sum') # NLL이랑 같음
        second_term /= x.shape[0]
        
        # 원래는 -Regular + Reconstruct
        # 하지만, Maximize를 시켜야 하기 때문에 부호를 뒤집어서 Regular - Reconstruct
        # Regular의 경우 KL을 계산하고 끝
        # Reconstruct의 경우 BCE 수식 자체가 의도하는 Reconstruct에 음수가 붙는 것이라
        # 아래와 같이 더해주면 된다.
        
        elbo = first_term + second_term # 이건 -ELBO임을 알고 있어야 한다.
        
        return elbo # ELBO를 최대화하는 게 목적이기 떄문에 Negative