#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { AwsSagemakerRlCartpoleStack } from '../lib/aws-sagemaker-rl-cartpole-stack';

const app = new cdk.App();

const targetRegion: string = process.env.CDK_DEFAULT_REGION ?? 'ap-northeast-1';
const targetAccount: string | undefined = process.env.CDK_DEFAULT_ACCOUNT;

new AwsSagemakerRlCartpoleStack(app, 'AwsSagemakerRlCartpoleStack', {
  env: { account: targetAccount, region: targetRegion },
});
